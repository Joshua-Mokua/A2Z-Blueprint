"""
================================================================================
A2Z MIS 360 — Standard #73: Liquidity Risk (LCR / NSFR) Engine
================================================================================

Risk classification: Cat B (deterministic Basel III regulatory ratios)

Computes Basel III + CBK liquidity risk metrics:
    - hqla_value(holdings)              -- High Quality Liquid Assets with haircuts
    - net_cash_outflows_30d(...)        -- 30-day stressed outflows minus inflows
    - lcr(...)                          -- Liquidity Coverage Ratio
    - available_stable_funding(...)     -- ASF for NSFR
    - required_stable_funding(...)      -- RSF for NSFR
    - nsfr(...)                         -- Net Stable Funding Ratio

Basel III + CBK compliance thresholds:
    LCR  : >= 100% (Basel III final calibration; CBK requires same)
    NSFR : >= 100% (Basel III; CBK quarterly reporting)

HQLA classification (Basel III):
    Level 1      : Cash, central bank reserves, govt securities (0% haircut)
    Level 2A     : Sovereign/PSE/MDB securities (15% haircut)
    Level 2B     : Corporate bonds (50% haircut), equities
    Cap          : Level 2 cannot exceed 40% of total HQLA;
                   Level 2B cannot exceed 15% of total HQLA

Stressed outflow run-off rates (Basel III standardised):
    Retail deposits (stable)     : 5%
    Retail deposits (less stable): 10%
    Operational SME deposits     : 25%
    Non-financial corporate      : 40%
    Financial counterparty       : 100%
    Undrawn credit facilities    : 10%

Honesty rules applied:
    Rule 1: ratios = None when denominator <= 0 (NCO=0 or RSF=0)
    Rule 6: holdings/deposits with missing classification surfaced in
            `excluded_count` (NEVER silently classified into highest-quality bucket)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Basel III HQLA classifications
HQLA_LEVELS: Tuple[str, ...] = ("LEVEL_1", "LEVEL_2A", "LEVEL_2B")

# Haircuts byte-for-byte per Basel III standardised
HQLA_HAIRCUT_PCT: Dict[str, Decimal] = {
    "LEVEL_1": Decimal("0"),
    "LEVEL_2A": Decimal("15"),
    "LEVEL_2B": Decimal("50"),
}

# Caps on Level 2 within total HQLA
LEVEL_2_TOTAL_CAP_PCT = Decimal("40")    # Level 2A + 2B <= 40% of total HQLA
LEVEL_2B_CAP_PCT = Decimal("15")         # Level 2B alone <= 15% of total HQLA

# Compliance thresholds
# v7.0.1: LCR_MIN_PCT and NSFR_MIN_PCT now sourced from system_invariants
# registry (single source of truth). Defensive fallback if registry import
# fails (Rule 6 honesty).
try:
    from utils.system_invariants import get_threshold as _get_invariant
    _lcr_from_registry = _get_invariant("LCR_MIN")
    _nsfr_from_registry = _get_invariant("NSFR_MIN")
    LCR_MIN_PCT = (
        _lcr_from_registry if _lcr_from_registry is not None
        else Decimal("100")
    )
    NSFR_MIN_PCT = (
        _nsfr_from_registry if _nsfr_from_registry is not None
        else Decimal("100")
    )
except ImportError:
    LCR_MIN_PCT = Decimal("100")
    NSFR_MIN_PCT = Decimal("100")

# Status thresholds
LCR_GREEN_MIN = Decimal("110")  # 10% buffer above minimum = GREEN
LCR_AMBER_MIN = Decimal("100")
NSFR_GREEN_MIN = Decimal("110")
NSFR_AMBER_MIN = Decimal("100")

# Outflow run-off rates (Basel III standardised) — % of balance assumed to leave
OUTFLOW_RATES_PCT: Dict[str, Decimal] = {
    "RETAIL_DEPOSITS_STABLE": Decimal("5"),
    "RETAIL_DEPOSITS_LESS_STABLE": Decimal("10"),
    "SME_OPERATIONAL": Decimal("25"),
    "CORPORATE_NON_FINANCIAL": Decimal("40"),
    "FINANCIAL_COUNTERPARTY": Decimal("100"),
    "UNDRAWN_CREDIT_FACILITIES": Decimal("10"),
    "UNDRAWN_LIQUIDITY_FACILITIES": Decimal("30"),
    "DERIVATIVES_NET_OUTFLOW": Decimal("100"),
}

# Inflow rates (capped per Basel III at 75% of outflows)
INFLOW_RATES_PCT: Dict[str, Decimal] = {
    "RETAIL_LOAN_INFLOWS": Decimal("50"),
    "WHOLESALE_LOAN_INFLOWS": Decimal("50"),
    "SECURED_LENDING": Decimal("100"),
    "OPERATIONAL_DEPOSITS_HELD": Decimal("0"),
}

INFLOW_CAP_PCT_OF_OUTFLOWS = Decimal("75")

# ASF factors (NSFR) — % of liability counted as stable funding
ASF_FACTORS_PCT: Dict[str, Decimal] = {
    "TIER_1_CAPITAL": Decimal("100"),
    "TIER_2_CAPITAL": Decimal("100"),
    "RETAIL_DEPOSITS_LT_1Y": Decimal("90"),
    "WHOLESALE_FUNDING_LT_1Y": Decimal("50"),
    "OPERATIONAL_DEPOSITS": Decimal("50"),
    "OTHER_LIABILITIES_LT_6M": Decimal("0"),
}

# RSF factors (NSFR) — % of asset requiring stable funding
RSF_FACTORS_PCT: Dict[str, Decimal] = {
    "CASH": Decimal("0"),
    "CENTRAL_BANK_RESERVES": Decimal("0"),
    "LEVEL_1_HQLA": Decimal("5"),
    "LEVEL_2A_HQLA": Decimal("15"),
    "LEVEL_2B_HQLA": Decimal("50"),
    "RETAIL_LOANS_LT_1Y": Decimal("50"),
    "RETAIL_LOANS_GTE_1Y": Decimal("65"),
    "CORPORATE_LOANS_LT_1Y": Decimal("50"),
    "CORPORATE_LOANS_GTE_1Y": Decimal("85"),
    "MORTGAGE_LOANS": Decimal("65"),
    "OTHER_ASSETS": Decimal("100"),
}


@dataclass
class HqlaHolding:
    asset_id: str
    level: str  # LEVEL_1 / LEVEL_2A / LEVEL_2B
    market_value_kes: Optional[Decimal] = None


@dataclass
class CashFlowItem:
    item_id: str
    category: str  # uses OUTFLOW_RATES_PCT or INFLOW_RATES_PCT keys
    direction: str  # OUTFLOW or INFLOW
    balance_kes: Optional[Decimal] = None


@dataclass
class FundingItem:
    item_id: str
    category: str  # uses ASF_FACTORS_PCT keys
    balance_kes: Optional[Decimal] = None


@dataclass
class AssetItem:
    item_id: str
    category: str  # uses RSF_FACTORS_PCT keys
    balance_kes: Optional[Decimal] = None


class LiquidityRiskEngine:
    """Deterministic Basel III LCR + NSFR computation."""

    @staticmethod
    def hqla_value(holdings: List[HqlaHolding]) -> Dict[str, Any]:
        """
        Apply haircuts and Level 2 caps.
        Rule 6: holdings with None market_value or unknown level excluded.
        """
        l1 = Decimal("0")
        l2a = Decimal("0")
        l2b = Decimal("0")
        excluded = []
        for h in holdings:
            if h.market_value_kes is None:
                excluded.append(h.asset_id)
                continue
            if h.level not in HQLA_LEVELS:
                excluded.append(h.asset_id)
                continue
            haircut = HQLA_HAIRCUT_PCT[h.level]
            after_haircut = h.market_value_kes * (Decimal("100") - haircut) / Decimal("100")
            if h.level == "LEVEL_1":
                l1 += after_haircut
            elif h.level == "LEVEL_2A":
                l2a += after_haircut
            else:
                l2b += after_haircut

        # Apply caps
        gross_total = l1 + l2a + l2b
        if gross_total <= 0:
            return {
                "level_1_kes": "0",
                "level_2a_kes": "0",
                "level_2b_kes": "0",
                "total_hqla_kes": "0",
                "excluded_count": len(excluded),
                "reason": "no_hqla_holdings",
            }

        # Level 2B capped at 15% of total HQLA
        # Iteratively adjust: total = L1 + min(L2A+L2B, L1*40/60) and L2B portion capped
        # Standard approach: compute notional total, then cap excesses
        # Simplified deterministic cap:
        total_with_caps = l1
        # Allow L2A up to (L1 * 40 / 60) i.e. L2 <= 40% of total => L2 <= 2/3 of L1
        max_l2 = (l1 * Decimal("2") / Decimal("3")).quantize(Decimal("0.01"))
        capped_l2_total = min(l2a + l2b, max_l2)
        # Within L2, cap L2B at 15/40 of L2 portion = L1 * 15/60 = L1/4
        max_l2b = (l1 * Decimal("0.25")).quantize(Decimal("0.01"))
        capped_l2b = min(l2b, max_l2b)
        # Adjust L2A accordingly
        capped_l2a = min(l2a, capped_l2_total - capped_l2b)
        if capped_l2a < 0:
            capped_l2a = Decimal("0")
        total_with_caps = l1 + capped_l2a + capped_l2b

        return {
            "level_1_kes": str(l1.quantize(Decimal("0.01"))),
            "level_2a_kes": str(l2a.quantize(Decimal("0.01"))),
            "level_2b_kes": str(l2b.quantize(Decimal("0.01"))),
            "level_2a_after_cap_kes": str(capped_l2a.quantize(Decimal("0.01"))),
            "level_2b_after_cap_kes": str(capped_l2b.quantize(Decimal("0.01"))),
            "gross_total_kes": str(gross_total.quantize(Decimal("0.01"))),
            "total_hqla_kes": str(total_with_caps.quantize(Decimal("0.01"))),
            "cap_applied": gross_total > total_with_caps,
            "excluded_count": len(excluded),
        }

    @staticmethod
    def net_cash_outflows_30d(items: List[CashFlowItem]) -> Dict[str, Any]:
        """
        Compute net cash outflows over 30-day stress horizon.
        Rule 6: items with missing balance or unknown category excluded.
        """
        total_outflows = Decimal("0")
        total_inflows = Decimal("0")
        excluded = []
        for it in items:
            if it.balance_kes is None:
                excluded.append(it.item_id)
                continue
            if it.direction == "OUTFLOW":
                rate = OUTFLOW_RATES_PCT.get(it.category)
                if rate is None:
                    excluded.append(it.item_id)
                    continue
                total_outflows += it.balance_kes * rate / Decimal("100")
            elif it.direction == "INFLOW":
                rate = INFLOW_RATES_PCT.get(it.category)
                if rate is None:
                    excluded.append(it.item_id)
                    continue
                total_inflows += it.balance_kes * rate / Decimal("100")
            else:
                excluded.append(it.item_id)

        # Cap inflows at 75% of outflows
        max_inflows = total_outflows * INFLOW_CAP_PCT_OF_OUTFLOWS / Decimal("100")
        capped_inflows = min(total_inflows, max_inflows)
        net_outflows = total_outflows - capped_inflows

        return {
            "total_outflows_kes": str(total_outflows.quantize(Decimal("0.01"))),
            "total_inflows_kes": str(total_inflows.quantize(Decimal("0.01"))),
            "capped_inflows_kes": str(capped_inflows.quantize(Decimal("0.01"))),
            "net_outflows_kes": str(net_outflows.quantize(Decimal("0.01"))),
            "excluded_count": len(excluded),
        }

    @classmethod
    def lcr(
        cls,
        hqla_holdings: List[HqlaHolding],
        cash_flows: List[CashFlowItem],
    ) -> Dict[str, Any]:
        """
        LCR = HQLA / Net Cash Outflows × 100. Rule 1: None on NCO<=0.
        """
        hqla = cls.hqla_value(hqla_holdings)
        nco = cls.net_cash_outflows_30d(cash_flows)
        hqla_total = Decimal(hqla["total_hqla_kes"])
        nco_total = Decimal(nco["net_outflows_kes"])

        if nco_total <= 0:
            return {
                "lcr_pct": None,
                "hqla_total_kes": str(hqla_total),
                "net_outflows_kes": str(nco_total),
                "min_required_pct": str(LCR_MIN_PCT),
                "status": "NO_DATA",
                "reason": "net_outflows_zero_or_negative",
            }

        ratio = (hqla_total / nco_total) * Decimal("100")

        if ratio >= LCR_GREEN_MIN:
            status = "GREEN"
        elif ratio >= LCR_AMBER_MIN:
            status = "AMBER"
        else:
            status = "RED"  # below regulatory minimum

        return {
            "lcr_pct": str(ratio.quantize(Decimal("0.01"))),
            "hqla_total_kes": str(hqla_total),
            "net_outflows_kes": str(nco_total),
            "min_required_pct": str(LCR_MIN_PCT),
            "status": status,
            "compliant": ratio >= LCR_MIN_PCT,
            "hqla_breakdown": hqla,
            "nco_breakdown": nco,
        }

    @staticmethod
    def available_stable_funding(funding: List[FundingItem]) -> Dict[str, Any]:
        """ASF = sum(balance × ASF factor). Rule 6: missing items excluded."""
        total = Decimal("0")
        excluded = []
        breakdown: Dict[str, Decimal] = {}
        for f in funding:
            if f.balance_kes is None:
                excluded.append(f.item_id)
                continue
            factor = ASF_FACTORS_PCT.get(f.category)
            if factor is None:
                excluded.append(f.item_id)
                continue
            asf = f.balance_kes * factor / Decimal("100")
            total += asf
            breakdown[f.category] = breakdown.get(f.category, Decimal("0")) + asf
        return {
            "total_asf_kes": str(total.quantize(Decimal("0.01"))),
            "excluded_count": len(excluded),
            "by_category": {k: str(v.quantize(Decimal("0.01"))) for k, v in breakdown.items()},
        }

    @staticmethod
    def required_stable_funding(assets: List[AssetItem]) -> Dict[str, Any]:
        """RSF = sum(balance × RSF factor). Rule 6: missing items excluded."""
        total = Decimal("0")
        excluded = []
        breakdown: Dict[str, Decimal] = {}
        for a in assets:
            if a.balance_kes is None:
                excluded.append(a.item_id)
                continue
            factor = RSF_FACTORS_PCT.get(a.category)
            if factor is None:
                excluded.append(a.item_id)
                continue
            rsf = a.balance_kes * factor / Decimal("100")
            total += rsf
            breakdown[a.category] = breakdown.get(a.category, Decimal("0")) + rsf
        return {
            "total_rsf_kes": str(total.quantize(Decimal("0.01"))),
            "excluded_count": len(excluded),
            "by_category": {k: str(v.quantize(Decimal("0.01"))) for k, v in breakdown.items()},
        }

    @classmethod
    def nsfr(
        cls,
        funding: List[FundingItem],
        assets: List[AssetItem],
    ) -> Dict[str, Any]:
        """NSFR = ASF / RSF × 100. Rule 1: None on RSF<=0."""
        asf = cls.available_stable_funding(funding)
        rsf = cls.required_stable_funding(assets)
        asf_total = Decimal(asf["total_asf_kes"])
        rsf_total = Decimal(rsf["total_rsf_kes"])

        if rsf_total <= 0:
            return {
                "nsfr_pct": None,
                "asf_kes": str(asf_total),
                "rsf_kes": str(rsf_total),
                "min_required_pct": str(NSFR_MIN_PCT),
                "status": "NO_DATA",
                "reason": "rsf_zero_or_negative",
            }

        ratio = (asf_total / rsf_total) * Decimal("100")

        if ratio >= NSFR_GREEN_MIN:
            status = "GREEN"
        elif ratio >= NSFR_AMBER_MIN:
            status = "AMBER"
        else:
            status = "RED"

        return {
            "nsfr_pct": str(ratio.quantize(Decimal("0.01"))),
            "asf_kes": str(asf_total),
            "rsf_kes": str(rsf_total),
            "min_required_pct": str(NSFR_MIN_PCT),
            "status": status,
            "compliant": ratio >= NSFR_MIN_PCT,
            "asf_breakdown": asf,
            "rsf_breakdown": rsf,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _hqla(**kw):
    defaults = dict(asset_id="A1", level="LEVEL_1", market_value_kes=Decimal("100000000"))
    defaults.update(kw)
    return HqlaHolding(**defaults)


def _cf(**kw):
    defaults = dict(item_id="I1", category="RETAIL_DEPOSITS_STABLE",
                    direction="OUTFLOW", balance_kes=Decimal("100000000"))
    defaults.update(kw)
    return CashFlowItem(**defaults)


def _test_hqla_level1_no_haircut():
    h = [_hqla(market_value_kes=Decimal("100000000"))]
    r = LiquidityRiskEngine.hqla_value(h)
    assert r["level_1_kes"] == "100000000.00"


def _test_hqla_level2a_haircut():
    h = [_hqla(level="LEVEL_2A", market_value_kes=Decimal("100000000"))]
    r = LiquidityRiskEngine.hqla_value(h)
    # 15% haircut
    assert r["level_2a_kes"] == "85000000.00"


def _test_hqla_level2b_haircut():
    h = [_hqla(level="LEVEL_2B", market_value_kes=Decimal("100000000"))]
    r = LiquidityRiskEngine.hqla_value(h)
    # 50% haircut
    assert r["level_2b_kes"] == "50000000.00"


def _test_hqla_excluded_rule6():
    h = [_hqla(market_value_kes=None)]
    r = LiquidityRiskEngine.hqla_value(h)
    assert r["excluded_count"] == 1


def _test_haircut_thresholds_byte_for_byte():
    assert HQLA_HAIRCUT_PCT["LEVEL_1"] == Decimal("0")
    assert HQLA_HAIRCUT_PCT["LEVEL_2A"] == Decimal("15")
    assert HQLA_HAIRCUT_PCT["LEVEL_2B"] == Decimal("50")


def _test_outflow_rates_byte_for_byte():
    assert OUTFLOW_RATES_PCT["RETAIL_DEPOSITS_STABLE"] == Decimal("5")
    assert OUTFLOW_RATES_PCT["FINANCIAL_COUNTERPARTY"] == Decimal("100")
    assert OUTFLOW_RATES_PCT["CORPORATE_NON_FINANCIAL"] == Decimal("40")


def _test_nco_basic():
    """100M retail stable @ 5% = 5M outflow. No inflow → NCO=5M."""
    cf = [_cf(category="RETAIL_DEPOSITS_STABLE",
              balance_kes=Decimal("100000000"))]
    r = LiquidityRiskEngine.net_cash_outflows_30d(cf)
    assert r["total_outflows_kes"] == "5000000.00"
    assert r["net_outflows_kes"] == "5000000.00"


def _test_nco_inflow_capped_at_75pct():
    """Inflows capped at 75% of outflows."""
    cf = [
        _cf(item_id="O1", category="CORPORATE_NON_FINANCIAL",
            direction="OUTFLOW", balance_kes=Decimal("100000000")),  # 40M outflow
        _cf(item_id="I1", category="WHOLESALE_LOAN_INFLOWS",
            direction="INFLOW", balance_kes=Decimal("100000000")),  # 50M inflow but capped at 30M
    ]
    r = LiquidityRiskEngine.net_cash_outflows_30d(cf)
    # Outflows = 40M, inflows = 50M raw, cap = 30M. Net = 40 - 30 = 10M
    assert r["total_outflows_kes"] == "40000000.00"
    assert r["capped_inflows_kes"] == "30000000.00"
    assert r["net_outflows_kes"] == "10000000.00"


def _test_lcr_compliant():
    h = [_hqla(market_value_kes=Decimal("100000000"))]
    cf = [_cf(category="RETAIL_DEPOSITS_STABLE",
              balance_kes=Decimal("100000000"))]
    r = LiquidityRiskEngine.lcr(h, cf)
    # HQLA 100M / NCO 5M = 2000% LCR
    assert r["status"] == "GREEN"
    assert r["compliant"] is True


def _test_lcr_breach():
    """LCR < 100% = RED."""
    h = [_hqla(market_value_kes=Decimal("1000000"))]  # 1M HQLA
    cf = [_cf(category="CORPORATE_NON_FINANCIAL",
              balance_kes=Decimal("100000000"))]  # 40M outflow
    r = LiquidityRiskEngine.lcr(h, cf)
    assert r["status"] == "RED"
    assert r["compliant"] is False


def _test_lcr_zero_outflows_rule1():
    """Rule 1: NCO=0 → LCR=None."""
    h = [_hqla(market_value_kes=Decimal("100000000"))]
    r = LiquidityRiskEngine.lcr(h, [])
    assert r["lcr_pct"] is None
    assert r["status"] == "NO_DATA"


def _test_nsfr_compliant():
    funding = [FundingItem(item_id="F1", category="RETAIL_DEPOSITS_LT_1Y",
                          balance_kes=Decimal("1000000000"))]  # ASF = 900M
    assets = [AssetItem(item_id="A1", category="RETAIL_LOANS_GTE_1Y",
                       balance_kes=Decimal("1000000000"))]  # RSF = 650M
    r = LiquidityRiskEngine.nsfr(funding, assets)
    # 900/650 = 138.46%
    assert r["status"] == "GREEN"
    assert r["compliant"] is True


def _test_nsfr_breach():
    funding = [FundingItem(item_id="F1", category="WHOLESALE_FUNDING_LT_1Y",
                          balance_kes=Decimal("100000000"))]  # 50M ASF
    assets = [AssetItem(item_id="A1", category="OTHER_ASSETS",
                       balance_kes=Decimal("1000000000"))]  # 1B RSF
    r = LiquidityRiskEngine.nsfr(funding, assets)
    assert r["status"] == "RED"


def _test_nsfr_rsf_zero_rule1():
    funding = [FundingItem(item_id="F1", category="RETAIL_DEPOSITS_LT_1Y",
                          balance_kes=Decimal("1000000000"))]
    r = LiquidityRiskEngine.nsfr(funding, [])
    assert r["nsfr_pct"] is None


def _test_asf_factors_byte_for_byte():
    assert ASF_FACTORS_PCT["TIER_1_CAPITAL"] == Decimal("100")
    assert ASF_FACTORS_PCT["RETAIL_DEPOSITS_LT_1Y"] == Decimal("90")
    assert ASF_FACTORS_PCT["WHOLESALE_FUNDING_LT_1Y"] == Decimal("50")


def _test_rsf_factors_byte_for_byte():
    assert RSF_FACTORS_PCT["CASH"] == Decimal("0")
    assert RSF_FACTORS_PCT["LEVEL_1_HQLA"] == Decimal("5")
    assert RSF_FACTORS_PCT["MORTGAGE_LOANS"] == Decimal("65")
    assert RSF_FACTORS_PCT["CORPORATE_LOANS_GTE_1Y"] == Decimal("85")


def _test_compliance_thresholds_byte_for_byte():
    assert LCR_MIN_PCT == Decimal("100")
    assert NSFR_MIN_PCT == Decimal("100")
    assert INFLOW_CAP_PCT_OF_OUTFLOWS == Decimal("75")


def self_test() -> bool:
    tests = [
        _test_hqla_level1_no_haircut,
        _test_hqla_level2a_haircut,
        _test_hqla_level2b_haircut,
        _test_hqla_excluded_rule6,
        _test_haircut_thresholds_byte_for_byte,
        _test_outflow_rates_byte_for_byte,
        _test_nco_basic,
        _test_nco_inflow_capped_at_75pct,
        _test_lcr_compliant,
        _test_lcr_breach,
        _test_lcr_zero_outflows_rule1,
        _test_nsfr_compliant,
        _test_nsfr_breach,
        _test_nsfr_rsf_zero_rule1,
        _test_asf_factors_byte_for_byte,
        _test_rsf_factors_byte_for_byte,
        _test_compliance_thresholds_byte_for_byte,
    ]
    print("=" * 60)
    print("Liquidity Risk Engine — Self-Tests (#73)")
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

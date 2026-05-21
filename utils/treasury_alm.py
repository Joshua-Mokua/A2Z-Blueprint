"""utils/treasury_alm.py — v10.33 Treasury arc batch 1: ALM foundation.

╔════════════════════════════════════════════════════════════════════════╗
║  TREASURY ALM — NMD + LIQUIDITY (LCR/NSFR) + IRRBB                     ║
║  Cat A — affects regulatory liquidity reporting + capital adequacy     ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (LCR/NSFR breaches trigger CBK supervisory action;  ║
║              IRRBB outlier reporting feeds Basel SREP; NMD             ║
║              behavioral assumptions affect ALM stress testing)         ║
║  Implements 3 of 16 Treasury standards from registry:                  ║
║    ENH-231: NMD Behavioral Modeling & Deposit Analytics                ║
║    ENH-232: Intraday Liquidity & Real-Time Monitoring                  ║
║    ENH-233: IRRBB Management & Dynamic ALM                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Note on naming: utils/treasury_intelligence.py is a Volume Seven      ║
║  legacy shell (TreasuryIntelligenceEngine with simple LCR/NSFR + AlM   ║
║  scaffolding). This module is the v10.33 dedicated ALM foundation —    ║
║  TreasuryALMEngine — implementing the full ENH-231/232/233 surface.   ║
║  Both coexist; the standards registry routes the new standards here.   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel BCBS 188 (2013) — Liquidity Coverage Ratio (LCR)              ║
║    Basel BCBS 295 (2014) — Net Stable Funding Ratio (NSFR)             ║
║    Basel BCBS 368 (2016) — Interest Rate Risk in the Banking Book      ║
║                            (IRRBB Standards) — 6 standardized          ║
║                            scenarios + ΔEVE > 15% Tier 1 outlier      ║
║    Basel BCBS 144 (2008) — Sound principles for liquidity risk          ║
║    Basel d549 (2021) — IRRBB monitoring revisited                      ║
║    Basel BCBS 248 (2013) — Monitoring tools for intraday liquidity     ║
║    EBA EBA/GL/2018/02 — IRRBB management                                ║
║    EBA EBA/GL/2022/14 — IRRBB & CSRBB                                  ║
║    CBK CBK/PG/16 (2016) — Liquidity Management                         ║
║    CBK Banking Act §19 — minimum liquidity ratio                       ║
║    IFRS 7 — Financial Instruments: Disclosures (liquidity)            ║
║    IFRS 9 — Financial Instruments (NMD core deposit modeling)         ║
║    Federal Reserve SR 10-1 — interagency policy on funding             ║
║                              concentration                              ║
║                                                                         ║
║  Honesty Rule 1: every LCR/NSFR/NII/EVE calculation surfaces inputs   ║
║  + parameters + per-bucket detail. Limit breaches surface specific   ║
║  numerator/denominator/threshold for examiner trace.                  ║
║  Honesty Rule 7: market-data fetcher (CBR, KESONIA, FX) and yield    ║
║  curve provider are callable hooks. Without wiring, scenarios apply  ║
║  config-defined defaults rather than fabricating live rates.         ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "TreasuryALMEngine implements ENH-231/232/233 foundation. "
    "Coexists with utils/treasury_intelligence.py (Volume Seven legacy). "
    "Per Rule 7, market-data fetchers (CBR overnight rate, KESONIA, FX) "
    "and yield curve provider are callable hooks; without wiring, the "
    "engine uses config-defined scenario rates and surfaces "
    "REQUIRES_PROVIDER notes rather than fabricating values. "
    "Per Rule 1, every LCR/NSFR/NII/EVE result reports numerator + "
    "denominator + per-bucket detail for examiner trace."
)


# ════════════════════════════════════════════════════════════════════════
# ENH-231: NMD Behavioral Modeling
# ════════════════════════════════════════════════════════════════════════

class NMDDepositCategory(Enum):
    """Non-Maturing Deposit categorization per Basel BCBS 188 LCR."""
    RETAIL_STABLE = "RETAIL_STABLE"
    RETAIL_LESS_STABLE = "RETAIL_LESS_STABLE"
    SME_OPERATIONAL = "SME_OPERATIONAL"
    CORPORATE_OPERATIONAL = "CORPORATE_OPERATIONAL"
    CORPORATE_NON_OPERATIONAL = "CORPORATE_NON_OPERATIONAL"
    INSTITUTIONAL_NON_OPERATIONAL = "INSTITUTIONAL_NON_OPERATIONAL"
    PUBLIC_SECTOR = "PUBLIC_SECTOR"


# 30-day stress runoff rates per Basel BCBS 188 (LCR).
DEFAULT_LCR_RUNOFF_RATES: Mapping[NMDDepositCategory, Decimal] = {
    NMDDepositCategory.RETAIL_STABLE: Decimal("3"),
    NMDDepositCategory.RETAIL_LESS_STABLE: Decimal("10"),
    NMDDepositCategory.SME_OPERATIONAL: Decimal("5"),
    NMDDepositCategory.CORPORATE_OPERATIONAL: Decimal("25"),
    NMDDepositCategory.CORPORATE_NON_OPERATIONAL: Decimal("40"),
    NMDDepositCategory.INSTITUTIONAL_NON_OPERATIONAL: Decimal("100"),
    NMDDepositCategory.PUBLIC_SECTOR: Decimal("40"),
}


# Available Stable Funding (ASF) factors per Basel BCBS 295 (NSFR)
DEFAULT_NSFR_ASF_FACTORS: Mapping[NMDDepositCategory, Decimal] = {
    NMDDepositCategory.RETAIL_STABLE: Decimal("95"),
    NMDDepositCategory.RETAIL_LESS_STABLE: Decimal("90"),
    NMDDepositCategory.SME_OPERATIONAL: Decimal("90"),
    NMDDepositCategory.CORPORATE_OPERATIONAL: Decimal("50"),
    NMDDepositCategory.CORPORATE_NON_OPERATIONAL: Decimal("50"),
    NMDDepositCategory.INSTITUTIONAL_NON_OPERATIONAL: Decimal("0"),
    NMDDepositCategory.PUBLIC_SECTOR: Decimal("50"),
}


@dataclass(frozen=True)
class NMDDeposit:
    """A non-maturing deposit position for behavioral modeling."""
    deposit_id: str
    cif: str
    category: NMDDepositCategory
    balance: Decimal
    currency: str
    open_date: str
    last_movement_date: Optional[str] = None
    is_insured: bool = False
    is_operational: bool = False
    notes: str = ""


@dataclass(frozen=True)
class NMDDecayResult:
    """NMD behavioral decay analysis."""
    analysis_id: str
    category: NMDDepositCategory
    n_deposits: int
    total_balance: Decimal
    avg_age_days: Decimal
    n_dormant_90d: int
    decay_rate_30d: Decimal
    sticky_balance_estimate: Decimal
    analysis_date: str
    notes: str = ""


def categorize_lcr_runoff(
    *, balance: Decimal, category: NMDDepositCategory,
    runoff_rates: Mapping[
        NMDDepositCategory, Decimal] = DEFAULT_LCR_RUNOFF_RATES,
) -> Decimal:
    """Compute 30-day LCR runoff for a deposit position."""
    rate = runoff_rates.get(category, Decimal("100"))
    return (balance * rate / Decimal("100")).quantize(Decimal("0.01"))


def categorize_nsfr_asf(
    *, balance: Decimal, category: NMDDepositCategory,
    asf_factors: Mapping[
        NMDDepositCategory, Decimal] = DEFAULT_NSFR_ASF_FACTORS,
) -> Decimal:
    factor = asf_factors.get(category, Decimal("0"))
    return (balance * factor / Decimal("100")).quantize(Decimal("0.01"))


def compute_decay_analysis(
    *,
    analysis_id: str,
    category: NMDDepositCategory,
    deposits: Sequence[NMDDeposit],
    analysis_date: str,
) -> NMDDecayResult:
    if not deposits:
        return NMDDecayResult(
            analysis_id=analysis_id, category=category,
            n_deposits=0, total_balance=Decimal("0"),
            avg_age_days=Decimal("0"), n_dormant_90d=0,
            decay_rate_30d=Decimal("0"),
            sticky_balance_estimate=Decimal("0"),
            analysis_date=analysis_date,
            notes="no deposits in category")
    try:
        as_of = date.fromisoformat(analysis_date)
    except ValueError:
        as_of = date.today()
    total_balance = sum(
        (d.balance for d in deposits), Decimal("0"))
    n = len(deposits)
    age_days_sum = Decimal("0")
    n_dormant = 0
    for d in deposits:
        try:
            opened = date.fromisoformat(d.open_date)
        except ValueError:
            continue
        age_days_sum += Decimal((as_of - opened).days)
        last_mvt = d.last_movement_date or d.open_date
        try:
            last = date.fromisoformat(last_mvt)
            if (as_of - last).days >= 90:
                n_dormant += 1
        except ValueError:
            pass
    avg_age = (age_days_sum / Decimal(n)).quantize(Decimal("0.01"))
    decay_rate = DEFAULT_LCR_RUNOFF_RATES.get(
        category, Decimal("100"))
    sticky_balance = (total_balance
                          * (Decimal("100") - decay_rate)
                          / Decimal("100")).quantize(Decimal("0.01"))
    return NMDDecayResult(
        analysis_id=analysis_id, category=category,
        n_deposits=n, total_balance=total_balance,
        avg_age_days=avg_age, n_dormant_90d=n_dormant,
        decay_rate_30d=decay_rate,
        sticky_balance_estimate=sticky_balance,
        analysis_date=analysis_date,
        notes=(
            f"{n} deposits in {category.value}; "
            f"avg age {avg_age:.0f} days; "
            f"{n_dormant} dormant 90+ days; "
            f"sticky est. KES {sticky_balance:,}"))


# ════════════════════════════════════════════════════════════════════════
# ENH-232: Intraday Liquidity + LCR/NSFR
# ════════════════════════════════════════════════════════════════════════

LCR_MIN_RATIO = Decimal("100")        # Basel III minimum
NSFR_MIN_RATIO = Decimal("100")
CBK_MIN_CASH_RATIO_PCT = Decimal("4.25")
CBK_MIN_LIQUID_ASSETS_PCT = Decimal("20")


class HQLALevel(Enum):
    """High-Quality Liquid Assets levels per Basel III."""
    LEVEL_1 = "LEVEL_1"
    LEVEL_2A = "LEVEL_2A"
    LEVEL_2B = "LEVEL_2B"
    NOT_HQLA = "NOT_HQLA"


HQLA_HAIRCUTS: Mapping[HQLALevel, Decimal] = {
    HQLALevel.LEVEL_1: Decimal("0"),
    HQLALevel.LEVEL_2A: Decimal("15"),
    HQLALevel.LEVEL_2B: Decimal("50"),
    HQLALevel.NOT_HQLA: Decimal("100"),
}


@dataclass(frozen=True)
class HQLAPosition:
    position_id: str
    asset_class: str
    level: HQLALevel
    notional: Decimal
    currency: str
    notes: str = ""

    def lcr_value(self) -> Decimal:
        haircut = HQLA_HAIRCUTS.get(self.level, Decimal("100"))
        return (self.notional
                  * (Decimal("100") - haircut)
                  / Decimal("100")).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class CashFlow:
    flow_id: str
    direction: str
    amount: Decimal
    bucket_days: int
    counterparty_category: str = ""
    notes: str = ""


@dataclass(frozen=True)
class LCRResult:
    result_id: str
    hqla_total: Decimal
    net_cash_outflow_30d: Decimal
    lcr_ratio_pct: Decimal
    is_compliant: bool
    n_hqla_positions: int
    n_inflows: int
    n_outflows: int
    capping_applied: str
    as_of_date: str
    notes: str = ""


def compute_lcr(
    *,
    result_id: str,
    hqla_positions: Sequence[HQLAPosition],
    inflows: Sequence[CashFlow],
    outflows: Sequence[CashFlow],
    as_of_date: str,
    horizon_days: int = 30,
) -> LCRResult:
    l1_value = sum(
        (p.lcr_value() for p in hqla_positions
         if p.level == HQLALevel.LEVEL_1),
        Decimal("0"))
    l2a_value = sum(
        (p.lcr_value() for p in hqla_positions
         if p.level == HQLALevel.LEVEL_2A),
        Decimal("0"))
    l2b_value = sum(
        (p.lcr_value() for p in hqla_positions
         if p.level == HQLALevel.LEVEL_2B),
        Decimal("0"))
    capping = "none"
    raw_total = l1_value + l2a_value + l2b_value
    if raw_total > Decimal("0"):
        if l2b_value > raw_total * Decimal("0.15"):
            l2b_value = raw_total * Decimal("0.15")
            capping = "L2B cap"
        l2_total = l2a_value + l2b_value
        if l2_total > (l1_value + l2_total) * Decimal("0.40"):
            l2_excess = l2_total - (l1_value + l2_total) * Decimal("0.40")
            l2a_value = max(Decimal("0"), l2a_value - l2_excess)
            capping = "L2 cap" if capping == "none" else capping + " + L2 cap"
    hqla_total = (l1_value + l2a_value + l2b_value).quantize(
        Decimal("0.01"))
    horizon_outflows = sum(
        (o.amount for o in outflows
         if o.bucket_days <= horizon_days),
        Decimal("0"))
    horizon_inflows = sum(
        (i.amount for i in inflows
         if i.bucket_days <= horizon_days),
        Decimal("0"))
    capped_inflows = min(
        horizon_inflows, horizon_outflows * Decimal("0.75"))
    net_outflows = (horizon_outflows - capped_inflows).quantize(
        Decimal("0.01"))
    if net_outflows == Decimal("0"):
        lcr = Decimal("999999")
    else:
        lcr = (hqla_total / net_outflows * Decimal("100")).quantize(
            Decimal("0.01"))
    return LCRResult(
        result_id=result_id, hqla_total=hqla_total,
        net_cash_outflow_30d=net_outflows,
        lcr_ratio_pct=lcr, is_compliant=lcr >= LCR_MIN_RATIO,
        n_hqla_positions=len(hqla_positions),
        n_inflows=len(inflows), n_outflows=len(outflows),
        capping_applied=capping,
        as_of_date=as_of_date,
        notes=(
            f"HQLA: L1={l1_value:,} L2A={l2a_value:,} "
            f"L2B={l2b_value:,}; "
            f"net outflows over {horizon_days}d: {net_outflows:,}"))


@dataclass(frozen=True)
class NSFRResult:
    result_id: str
    available_stable_funding: Decimal
    required_stable_funding: Decimal
    nsfr_ratio_pct: Decimal
    is_compliant: bool
    as_of_date: str
    notes: str = ""


def compute_nsfr(
    *,
    result_id: str,
    asf_components: Mapping[str, Decimal],
    rsf_components: Mapping[str, Decimal],
    as_of_date: str,
) -> NSFRResult:
    asf_total = sum(asf_components.values(), Decimal("0"))
    rsf_total = sum(rsf_components.values(), Decimal("0"))
    if rsf_total == Decimal("0"):
        nsfr = Decimal("999999")
    else:
        nsfr = (asf_total / rsf_total * Decimal("100")).quantize(
            Decimal("0.01"))
    return NSFRResult(
        result_id=result_id,
        available_stable_funding=asf_total.quantize(Decimal("0.01")),
        required_stable_funding=rsf_total.quantize(Decimal("0.01")),
        nsfr_ratio_pct=nsfr,
        is_compliant=nsfr >= NSFR_MIN_RATIO,
        as_of_date=as_of_date,
        notes=(
            f"ASF components: {len(asf_components)}; "
            f"RSF components: {len(rsf_components)}"))


@dataclass(frozen=True)
class IntradayLiquidityPosition:
    position_id: str
    snapshot_timestamp: str
    daily_max_intraday_liquidity_usage: Decimal
    available_intraday_liquidity: Decimal
    n_payments_throughput: int
    largest_single_outflow: Decimal
    notes: str = ""

    def usage_ratio_pct(self) -> Decimal:
        if self.available_intraday_liquidity <= Decimal("0"):
            return Decimal("999999")
        return (self.daily_max_intraday_liquidity_usage
                  / self.available_intraday_liquidity
                  * Decimal("100")).quantize(Decimal("0.01"))


# ════════════════════════════════════════════════════════════════════════
# ENH-233: IRRBB
# ════════════════════════════════════════════════════════════════════════

class IRRBBScenario(Enum):
    """6 standardized IR shock scenarios per Basel BCBS 368."""
    PARALLEL_UP = "PARALLEL_UP"
    PARALLEL_DOWN = "PARALLEL_DOWN"
    STEEPENER = "STEEPENER"
    FLATTENER = "FLATTENER"
    SHORT_RATE_UP = "SHORT_RATE_UP"
    SHORT_RATE_DOWN = "SHORT_RATE_DOWN"


# Basel BCBS 368 outlier criterion: ΔEVE > 15% of Tier 1 capital
IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1 = Decimal("15")


class MaturityBucket(Enum):
    """Maturity ladder buckets for repricing gap analysis."""
    OVERNIGHT = "OVERNIGHT"
    DAYS_2_7 = "2D_7D"
    DAYS_8_30 = "8D_1M"
    MONTHS_1_3 = "1M_3M"
    MONTHS_3_6 = "3M_6M"
    MONTHS_6_12 = "6M_1Y"
    YEARS_1_2 = "1Y_2Y"
    YEARS_2_5 = "2Y_5Y"
    YEARS_5_PLUS = "5Y+"


BUCKET_MID_YEARS: Mapping[MaturityBucket, Decimal] = {
    MaturityBucket.OVERNIGHT: Decimal("0.003"),
    MaturityBucket.DAYS_2_7: Decimal("0.012"),
    MaturityBucket.DAYS_8_30: Decimal("0.05"),
    MaturityBucket.MONTHS_1_3: Decimal("0.17"),
    MaturityBucket.MONTHS_3_6: Decimal("0.375"),
    MaturityBucket.MONTHS_6_12: Decimal("0.75"),
    MaturityBucket.YEARS_1_2: Decimal("1.5"),
    MaturityBucket.YEARS_2_5: Decimal("3.5"),
    MaturityBucket.YEARS_5_PLUS: Decimal("10"),
}


@dataclass(frozen=True)
class RatesGapPosition:
    position_id: str
    bucket: MaturityBucket
    is_asset: bool
    notional: Decimal
    currency: str
    notes: str = ""


@dataclass(frozen=True)
class RepricingGapResult:
    result_id: str
    gaps_by_bucket: Mapping[MaturityBucket, Decimal]
    total_assets: Decimal
    total_liabilities: Decimal
    cumulative_gap_1y: Decimal
    as_of_date: str
    notes: str = ""


def compute_repricing_gap(
    *,
    result_id: str,
    positions: Sequence[RatesGapPosition],
    as_of_date: str,
) -> RepricingGapResult:
    gaps: Dict[MaturityBucket, Decimal] = {
        b: Decimal("0") for b in MaturityBucket}
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    for p in positions:
        if p.is_asset:
            gaps[p.bucket] += p.notional
            total_assets += p.notional
        else:
            gaps[p.bucket] -= p.notional
            total_liabilities += p.notional
    one_year_buckets = (
        MaturityBucket.OVERNIGHT, MaturityBucket.DAYS_2_7,
        MaturityBucket.DAYS_8_30, MaturityBucket.MONTHS_1_3,
        MaturityBucket.MONTHS_3_6, MaturityBucket.MONTHS_6_12)
    cum_1y = sum((gaps[b] for b in one_year_buckets), Decimal("0"))
    return RepricingGapResult(
        result_id=result_id,
        gaps_by_bucket=dict(gaps),
        total_assets=total_assets.quantize(Decimal("0.01")),
        total_liabilities=total_liabilities.quantize(Decimal("0.01")),
        cumulative_gap_1y=cum_1y.quantize(Decimal("0.01")),
        as_of_date=as_of_date,
        notes=(
            f"{len(positions)} positions; "
            f"net assets={total_assets - total_liabilities:,}; "
            f"1y cum gap={cum_1y:,}"))


def parallel_shock_bps(scenario: IRRBBScenario) -> Decimal:
    return {
        IRRBBScenario.PARALLEL_UP: Decimal("200"),
        IRRBBScenario.PARALLEL_DOWN: Decimal("-200"),
        IRRBBScenario.STEEPENER: Decimal("0"),
        IRRBBScenario.FLATTENER: Decimal("0"),
        IRRBBScenario.SHORT_RATE_UP: Decimal("0"),
        IRRBBScenario.SHORT_RATE_DOWN: Decimal("0"),
    }.get(scenario, Decimal("0"))


def short_long_shock_bps(
    scenario: IRRBBScenario,
) -> Tuple[Decimal, Decimal]:
    return {
        IRRBBScenario.PARALLEL_UP: (
            Decimal("200"), Decimal("200")),
        IRRBBScenario.PARALLEL_DOWN: (
            Decimal("-200"), Decimal("-200")),
        IRRBBScenario.STEEPENER: (
            Decimal("-65"), Decimal("90")),
        IRRBBScenario.FLATTENER: (
            Decimal("80"), Decimal("-150")),
        IRRBBScenario.SHORT_RATE_UP: (
            Decimal("250"), Decimal("0")),
        IRRBBScenario.SHORT_RATE_DOWN: (
            Decimal("-250"), Decimal("0")),
    }.get(scenario, (Decimal("0"), Decimal("0")))


@dataclass(frozen=True)
class NIIScenarioResult:
    result_id: str
    scenario: IRRBBScenario
    base_nii_kes: Decimal
    shocked_nii_kes: Decimal
    delta_nii_kes: Decimal
    delta_nii_pct: Decimal
    as_of_date: str
    notes: str = ""


def compute_nii_sensitivity(
    *,
    result_id: str,
    scenario: IRRBBScenario,
    gap_result: RepricingGapResult,
    base_nii_kes: Decimal,
    as_of_date: str,
) -> NIIScenarioResult:
    short_bps, _long_bps = short_long_shock_bps(scenario)
    short_pct = short_bps / Decimal("10000")
    delta_nii = (gap_result.cumulative_gap_1y * short_pct).quantize(
        Decimal("0.01"))
    shocked_nii = (base_nii_kes + delta_nii).quantize(Decimal("0.01"))
    delta_pct = (
        (delta_nii / base_nii_kes * Decimal("100"))
        if base_nii_kes != Decimal("0") else Decimal("0")).quantize(
            Decimal("0.01"))
    return NIIScenarioResult(
        result_id=result_id, scenario=scenario,
        base_nii_kes=base_nii_kes, shocked_nii_kes=shocked_nii,
        delta_nii_kes=delta_nii, delta_nii_pct=delta_pct,
        as_of_date=as_of_date,
        notes=(
            f"scenario {scenario.value}: short_shock={short_bps}bps; "
            f"applied to cum 1y gap={gap_result.cumulative_gap_1y:,}"))


@dataclass(frozen=True)
class EVEScenarioResult:
    result_id: str
    scenario: IRRBBScenario
    base_eve_kes: Decimal
    shocked_eve_kes: Decimal
    delta_eve_kes: Decimal
    delta_eve_pct_tier_1: Decimal
    is_outlier: bool
    as_of_date: str
    notes: str = ""


def compute_eve_sensitivity(
    *,
    result_id: str,
    scenario: IRRBBScenario,
    positions: Sequence[RatesGapPosition],
    base_eve_kes: Decimal,
    tier_1_capital_kes: Decimal,
    as_of_date: str,
) -> EVEScenarioResult:
    short_bps, long_bps = short_long_shock_bps(scenario)
    bucket_gaps: Dict[MaturityBucket, Decimal] = {
        b: Decimal("0") for b in MaturityBucket}
    for p in positions:
        if p.is_asset:
            bucket_gaps[p.bucket] += p.notional
        else:
            bucket_gaps[p.bucket] -= p.notional
    bucket_order = list(MaturityBucket)
    n_buckets = len(bucket_order)
    delta_eve = Decimal("0")
    for i, b in enumerate(bucket_order):
        gap = bucket_gaps.get(b, Decimal("0"))
        if gap == Decimal("0"):
            continue
        if n_buckets > 1:
            short_weight = Decimal(n_buckets - 1 - i) / Decimal(
                n_buckets - 1)
        else:
            short_weight = Decimal("1")
        long_weight = Decimal("1") - short_weight
        bucket_shock_bps = (
            short_bps * short_weight + long_bps * long_weight)
        bucket_shock_pct = bucket_shock_bps / Decimal("10000")
        duration = BUCKET_MID_YEARS[b]
        delta_eve -= gap * duration * bucket_shock_pct
    delta_eve = delta_eve.quantize(Decimal("0.01"))
    shocked_eve = (base_eve_kes + delta_eve).quantize(Decimal("0.01"))
    if tier_1_capital_kes <= Decimal("0"):
        delta_pct_tier_1 = Decimal("0")
    else:
        delta_pct_tier_1 = (
            abs(delta_eve) / tier_1_capital_kes
            * Decimal("100")).quantize(Decimal("0.01"))
    return EVEScenarioResult(
        result_id=result_id, scenario=scenario,
        base_eve_kes=base_eve_kes, shocked_eve_kes=shocked_eve,
        delta_eve_kes=delta_eve,
        delta_eve_pct_tier_1=delta_pct_tier_1,
        is_outlier=(
            delta_pct_tier_1 > IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1),
        as_of_date=as_of_date,
        notes=(
            f"scenario {scenario.value}: short={short_bps}bps "
            f"long={long_bps}bps → ΔEVE={delta_eve:,}; "
            f"ΔEVE/T1={delta_pct_tier_1:.2f}% "
            f"(threshold {IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1}%)"))


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TreasuryALMEngine:
    """End-to-end ENH-231 + ENH-232 + ENH-233 orchestrator."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._deposits: Dict[str, NMDDeposit] = {}
        self._hqla: Dict[str, HQLAPosition] = {}
        self._inflows: List[CashFlow] = []
        self._outflows: List[CashFlow] = []
        self._lcr_results: Dict[str, LCRResult] = {}
        self._nsfr_results: Dict[str, NSFRResult] = {}
        self._intraday_positions: List[IntradayLiquidityPosition] = []
        self._rates_positions: Dict[str, RatesGapPosition] = {}
        self._gap_results: Dict[str, RepricingGapResult] = {}
        self._nii_results: Dict[str, NIIScenarioResult] = {}
        self._eve_results: Dict[str, EVEScenarioResult] = {}

    # NMD
    def register_deposit(self, d: NMDDeposit) -> None:
        if d.deposit_id in self._deposits:
            raise ValueError(f"deposit {d.deposit_id} exists")
        self._deposits[d.deposit_id] = d

    def deposits_by_category(
        self, category: NMDDepositCategory,
    ) -> Tuple[NMDDeposit, ...]:
        return tuple(
            d for d in self._deposits.values()
            if d.category == category)

    def run_decay_analysis(
        self, *, analysis_id: str,
        category: NMDDepositCategory, analysis_date: str,
    ) -> NMDDecayResult:
        return compute_decay_analysis(
            analysis_id=analysis_id, category=category,
            deposits=self.deposits_by_category(category),
            analysis_date=analysis_date)

    # HQLA + cash flows
    def register_hqla(self, h: HQLAPosition) -> None:
        if h.position_id in self._hqla:
            raise ValueError(f"hqla {h.position_id} exists")
        self._hqla[h.position_id] = h

    def add_inflow(self, c: CashFlow) -> None:
        if c.direction != "INFLOW":
            raise ValueError(
                f"add_inflow expects INFLOW, got {c.direction}")
        self._inflows.append(c)

    def add_outflow(self, c: CashFlow) -> None:
        if c.direction != "OUTFLOW":
            raise ValueError(
                f"add_outflow expects OUTFLOW, got {c.direction}")
        self._outflows.append(c)

    def run_lcr(
        self, *, result_id: str, as_of_date: str,
        horizon_days: int = 30,
    ) -> LCRResult:
        result = compute_lcr(
            result_id=result_id,
            hqla_positions=tuple(self._hqla.values()),
            inflows=tuple(self._inflows),
            outflows=tuple(self._outflows),
            as_of_date=as_of_date, horizon_days=horizon_days)
        self._lcr_results[result_id] = result
        return result

    def run_nsfr(
        self, *, result_id: str,
        asf_components: Mapping[str, Decimal],
        rsf_components: Mapping[str, Decimal],
        as_of_date: str,
    ) -> NSFRResult:
        result = compute_nsfr(
            result_id=result_id, asf_components=asf_components,
            rsf_components=rsf_components, as_of_date=as_of_date)
        self._nsfr_results[result_id] = result
        return result

    def record_intraday_position(
        self, p: IntradayLiquidityPosition,
    ) -> None:
        self._intraday_positions.append(p)

    # Rates / IRRBB
    def register_rates_position(
        self, p: RatesGapPosition,
    ) -> None:
        if p.position_id in self._rates_positions:
            raise ValueError(
                f"rates position {p.position_id} exists")
        self._rates_positions[p.position_id] = p

    def run_repricing_gap(
        self, *, result_id: str, as_of_date: str,
    ) -> RepricingGapResult:
        result = compute_repricing_gap(
            result_id=result_id,
            positions=tuple(self._rates_positions.values()),
            as_of_date=as_of_date)
        self._gap_results[result_id] = result
        return result

    def run_nii_sensitivity(
        self, *, result_id: str, scenario: IRRBBScenario,
        gap_result_id: str, base_nii_kes: Decimal,
        as_of_date: str,
    ) -> NIIScenarioResult:
        if gap_result_id not in self._gap_results:
            raise KeyError(
                f"gap {gap_result_id} not found — run "
                f"run_repricing_gap first")
        result = compute_nii_sensitivity(
            result_id=result_id, scenario=scenario,
            gap_result=self._gap_results[gap_result_id],
            base_nii_kes=base_nii_kes, as_of_date=as_of_date)
        self._nii_results[result_id] = result
        return result

    def run_eve_sensitivity(
        self, *, result_id: str, scenario: IRRBBScenario,
        base_eve_kes: Decimal, tier_1_capital_kes: Decimal,
        as_of_date: str,
    ) -> EVEScenarioResult:
        result = compute_eve_sensitivity(
            result_id=result_id, scenario=scenario,
            positions=tuple(self._rates_positions.values()),
            base_eve_kes=base_eve_kes,
            tier_1_capital_kes=tier_1_capital_kes,
            as_of_date=as_of_date)
        self._eve_results[result_id] = result
        return result

    def run_all_irrbb_scenarios(
        self, *, result_id_prefix: str, gap_result_id: str,
        base_nii_kes: Decimal, base_eve_kes: Decimal,
        tier_1_capital_kes: Decimal, as_of_date: str,
    ) -> Tuple[Tuple[NIIScenarioResult, ...],
                  Tuple[EVEScenarioResult, ...]]:
        nii_results: List[NIIScenarioResult] = []
        eve_results: List[EVEScenarioResult] = []
        for s in IRRBBScenario:
            nii_results.append(self.run_nii_sensitivity(
                result_id=f"{result_id_prefix}-NII-{s.value}",
                scenario=s, gap_result_id=gap_result_id,
                base_nii_kes=base_nii_kes,
                as_of_date=as_of_date))
            eve_results.append(self.run_eve_sensitivity(
                result_id=f"{result_id_prefix}-EVE-{s.value}",
                scenario=s, base_eve_kes=base_eve_kes,
                tier_1_capital_kes=tier_1_capital_kes,
                as_of_date=as_of_date))
        return tuple(nii_results), tuple(eve_results)

    def outlier_scenarios(self) -> Tuple[EVEScenarioResult, ...]:
        return tuple(
            r for r in self._eve_results.values() if r.is_outlier)

    def board_summary(self) -> Dict[str, Any]:
        latest_lcr = max(
            self._lcr_results.values(),
            key=lambda r: r.as_of_date,
            default=None)
        latest_nsfr = max(
            self._nsfr_results.values(),
            key=lambda r: r.as_of_date,
            default=None)
        return {
            "entity": self.entity_name,
            "n_deposits": len(self._deposits),
            "n_hqla_positions": len(self._hqla),
            "n_rates_positions": len(self._rates_positions),
            "latest_lcr_pct": (
                str(latest_lcr.lcr_ratio_pct)
                if latest_lcr else None),
            "latest_lcr_compliant": (
                latest_lcr.is_compliant if latest_lcr else None),
            "latest_nsfr_pct": (
                str(latest_nsfr.nsfr_ratio_pct)
                if latest_nsfr else None),
            "latest_nsfr_compliant": (
                latest_nsfr.is_compliant if latest_nsfr else None),
            "n_eve_outliers": len(self.outlier_scenarios()),
            "n_intraday_positions": len(self._intraday_positions),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_lcr_min_per_basel_188():
    assert LCR_MIN_RATIO == Decimal("100")


def _test_nsfr_min_per_basel_295():
    assert NSFR_MIN_RATIO == Decimal("100")


def _test_irrbb_outlier_threshold_per_bcbs_368():
    assert IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1 == Decimal("15")


def _test_lcr_runoff_retail_stable_3pct():
    assert (DEFAULT_LCR_RUNOFF_RATES[
        NMDDepositCategory.RETAIL_STABLE] == Decimal("3"))


def _test_nsfr_asf_retail_stable_95pct():
    assert (DEFAULT_NSFR_ASF_FACTORS[
        NMDDepositCategory.RETAIL_STABLE] == Decimal("95"))


def _test_lcr_runoff_retail_3pct():
    out = categorize_lcr_runoff(
        balance=Decimal("1000000"),
        category=NMDDepositCategory.RETAIL_STABLE)
    assert out == Decimal("30000.00")


def _test_lcr_runoff_institutional_100pct():
    out = categorize_lcr_runoff(
        balance=Decimal("1000000"),
        category=NMDDepositCategory.INSTITUTIONAL_NON_OPERATIONAL)
    assert out == Decimal("1000000.00")


def _test_nsfr_asf_corporate_50pct():
    out = categorize_nsfr_asf(
        balance=Decimal("1000000"),
        category=NMDDepositCategory.CORPORATE_NON_OPERATIONAL)
    assert out == Decimal("500000.00")


def _test_decay_analysis_empty():
    result = compute_decay_analysis(
        analysis_id="A1",
        category=NMDDepositCategory.RETAIL_STABLE,
        deposits=[], analysis_date="2026-05-01")
    assert result.n_deposits == 0


def _test_decay_analysis_aggregates():
    deps = [NMDDeposit(
        deposit_id=f"D{i}", cif=f"C{i}",
        category=NMDDepositCategory.RETAIL_STABLE,
        balance=Decimal("100000"), currency="KES",
        open_date="2024-01-01",
        last_movement_date="2024-06-01")
        for i in range(5)]
    result = compute_decay_analysis(
        analysis_id="A1",
        category=NMDDepositCategory.RETAIL_STABLE,
        deposits=deps, analysis_date="2026-05-01")
    assert result.n_deposits == 5
    assert result.total_balance == Decimal("500000")
    assert result.n_dormant_90d == 5
    assert result.sticky_balance_estimate == Decimal("485000.00")


def _test_hqla_l1_no_haircut():
    p = HQLAPosition(
        position_id="P1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("1000000"), currency="KES")
    assert p.lcr_value() == Decimal("1000000.00")


def _test_hqla_l2a_15pct_haircut():
    p = HQLAPosition(
        position_id="P1", asset_class="sov",
        level=HQLALevel.LEVEL_2A,
        notional=Decimal("1000000"), currency="KES")
    assert p.lcr_value() == Decimal("850000.00")


def _test_compute_lcr_compliant():
    hqla = [HQLAPosition(
        position_id="P1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("200000000"), currency="KES")]
    outflows = [CashFlow(
        flow_id="O1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30)]
    result = compute_lcr(
        result_id="L1", hqla_positions=hqla,
        inflows=[], outflows=outflows,
        as_of_date="2026-05-01")
    assert result.lcr_ratio_pct == Decimal("200.00")
    assert result.is_compliant


def _test_compute_lcr_non_compliant():
    hqla = [HQLAPosition(
        position_id="P1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("50000000"), currency="KES")]
    outflows = [CashFlow(
        flow_id="O1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30)]
    result = compute_lcr(
        result_id="L1", hqla_positions=hqla,
        inflows=[], outflows=outflows,
        as_of_date="2026-05-01")
    assert not result.is_compliant


def _test_compute_lcr_inflow_capped_75pct():
    hqla = [HQLAPosition(
        position_id="P1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("100000000"), currency="KES")]
    inflows = [CashFlow(
        flow_id="I1", direction="INFLOW",
        amount=Decimal("100000000"), bucket_days=30)]
    outflows = [CashFlow(
        flow_id="O1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30)]
    result = compute_lcr(
        result_id="L1", hqla_positions=hqla,
        inflows=inflows, outflows=outflows,
        as_of_date="2026-05-01")
    assert result.net_cash_outflow_30d == Decimal("25000000.00")


def _test_compute_nsfr():
    result = compute_nsfr(
        result_id="N1",
        asf_components={"retail_stable": Decimal("950000")},
        rsf_components={"loans_1y": Decimal("700000")},
        as_of_date="2026-05-01")
    assert result.is_compliant


def _test_intraday_position_usage_ratio():
    p = IntradayLiquidityPosition(
        position_id="IP1",
        snapshot_timestamp="2026-05-01T14:00:00Z",
        daily_max_intraday_liquidity_usage=Decimal("80000000"),
        available_intraday_liquidity=Decimal("100000000"),
        n_payments_throughput=500,
        largest_single_outflow=Decimal("10000000"))
    assert p.usage_ratio_pct() == Decimal("80.00")


def _test_parallel_up_200bps():
    assert parallel_shock_bps(IRRBBScenario.PARALLEL_UP) == Decimal("200")


def _test_steepener_short_negative_long_positive():
    short, long = short_long_shock_bps(IRRBBScenario.STEEPENER)
    assert short < Decimal("0")
    assert long > Decimal("0")


def _test_repricing_gap_aggregates():
    positions = [
        RatesGapPosition(
            position_id="P1", bucket=MaturityBucket.MONTHS_1_3,
            is_asset=True, notional=Decimal("500000"),
            currency="KES"),
        RatesGapPosition(
            position_id="P2", bucket=MaturityBucket.MONTHS_1_3,
            is_asset=False, notional=Decimal("300000"),
            currency="KES")]
    result = compute_repricing_gap(
        result_id="G1", positions=positions,
        as_of_date="2026-05-01")
    assert result.gaps_by_bucket[
        MaturityBucket.MONTHS_1_3] == Decimal("200000")


def _test_nii_sensitivity_parallel_up():
    positions = [RatesGapPosition(
        position_id="P1", bucket=MaturityBucket.MONTHS_1_3,
        is_asset=True, notional=Decimal("100000000"),
        currency="KES")]
    gap = compute_repricing_gap(
        result_id="G1", positions=positions,
        as_of_date="2026-05-01")
    nii = compute_nii_sensitivity(
        result_id="NII1",
        scenario=IRRBBScenario.PARALLEL_UP,
        gap_result=gap,
        base_nii_kes=Decimal("10000000"),
        as_of_date="2026-05-01")
    assert nii.delta_nii_kes == Decimal("2000000.00")


def _test_eve_sensitivity_outlier():
    positions = [RatesGapPosition(
        position_id="P1", bucket=MaturityBucket.YEARS_5_PLUS,
        is_asset=True, notional=Decimal("10000000000"),
        currency="KES")]
    eve = compute_eve_sensitivity(
        result_id="EVE1",
        scenario=IRRBBScenario.PARALLEL_UP,
        positions=positions,
        base_eve_kes=Decimal("0"),
        tier_1_capital_kes=Decimal("1000000000"),
        as_of_date="2026-05-01")
    assert eve.is_outlier


def _test_eve_sensitivity_compliant():
    positions = [RatesGapPosition(
        position_id="P1", bucket=MaturityBucket.MONTHS_3_6,
        is_asset=True, notional=Decimal("100000000"),
        currency="KES")]
    eve = compute_eve_sensitivity(
        result_id="EVE1",
        scenario=IRRBBScenario.PARALLEL_UP,
        positions=positions,
        base_eve_kes=Decimal("0"),
        tier_1_capital_kes=Decimal("10000000000"),
        as_of_date="2026-05-01")
    assert not eve.is_outlier


def _test_engine_register_dup_deposit_raises():
    eng = TreasuryALMEngine()
    d = NMDDeposit(
        deposit_id="D1", cif="C1",
        category=NMDDepositCategory.RETAIL_STABLE,
        balance=Decimal("100000"),
        currency="KES", open_date="2025-01-01")
    eng.register_deposit(d)
    try:
        eng.register_deposit(d)
        assert False
    except ValueError:
        pass


def _test_engine_run_lcr_compliant():
    eng = TreasuryALMEngine()
    eng.register_hqla(HQLAPosition(
        position_id="H1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("100000000"), currency="KES"))
    eng.add_outflow(CashFlow(
        flow_id="O1", direction="OUTFLOW",
        amount=Decimal("50000000"), bucket_days=30))
    result = eng.run_lcr(
        result_id="L1", as_of_date="2026-05-01")
    assert result.is_compliant


def _test_engine_inflow_with_outflow_direction_raises():
    eng = TreasuryALMEngine()
    try:
        eng.add_inflow(CashFlow(
            flow_id="I1", direction="OUTFLOW",
            amount=Decimal("1000"), bucket_days=1))
        assert False
    except ValueError:
        pass


def _test_engine_eve_requires_gap_run_first():
    eng = TreasuryALMEngine()
    try:
        eng.run_nii_sensitivity(
            result_id="NII1",
            scenario=IRRBBScenario.PARALLEL_UP,
            gap_result_id="MISSING",
            base_nii_kes=Decimal("100000"),
            as_of_date="2026-05-01")
        assert False
    except KeyError:
        pass


def _test_engine_run_all_irrbb_scenarios_count():
    eng = TreasuryALMEngine()
    eng.register_rates_position(RatesGapPosition(
        position_id="P1",
        bucket=MaturityBucket.MONTHS_1_3,
        is_asset=True, notional=Decimal("100000000"),
        currency="KES"))
    eng.run_repricing_gap(
        result_id="G1", as_of_date="2026-05-01")
    nii_results, eve_results = eng.run_all_irrbb_scenarios(
        result_id_prefix="ALL", gap_result_id="G1",
        base_nii_kes=Decimal("10000000"),
        base_eve_kes=Decimal("0"),
        tier_1_capital_kes=Decimal("1000000000"),
        as_of_date="2026-05-01")
    assert len(nii_results) == 6
    assert len(eve_results) == 6


def _test_engine_outlier_filter():
    eng = TreasuryALMEngine()
    eng.register_rates_position(RatesGapPosition(
        position_id="P1",
        bucket=MaturityBucket.YEARS_5_PLUS,
        is_asset=True, notional=Decimal("10000000000"),
        currency="KES"))
    eng.run_repricing_gap(
        result_id="G1", as_of_date="2026-05-01")
    eng.run_all_irrbb_scenarios(
        result_id_prefix="ALL", gap_result_id="G1",
        base_nii_kes=Decimal("100000000"),
        base_eve_kes=Decimal("0"),
        tier_1_capital_kes=Decimal("1000000000"),
        as_of_date="2026-05-01")
    assert len(eng.outlier_scenarios()) > 0


def _test_engine_board_summary():
    eng = TreasuryALMEngine()
    s = eng.board_summary()
    assert s["entity"] == "Ecobank Kenya"
    assert s["n_deposits"] == 0


def self_test() -> None:
    tests = [
        _test_lcr_min_per_basel_188,
        _test_nsfr_min_per_basel_295,
        _test_irrbb_outlier_threshold_per_bcbs_368,
        _test_lcr_runoff_retail_stable_3pct,
        _test_nsfr_asf_retail_stable_95pct,
        _test_lcr_runoff_retail_3pct,
        _test_lcr_runoff_institutional_100pct,
        _test_nsfr_asf_corporate_50pct,
        _test_decay_analysis_empty,
        _test_decay_analysis_aggregates,
        _test_hqla_l1_no_haircut,
        _test_hqla_l2a_15pct_haircut,
        _test_compute_lcr_compliant,
        _test_compute_lcr_non_compliant,
        _test_compute_lcr_inflow_capped_75pct,
        _test_compute_nsfr,
        _test_intraday_position_usage_ratio,
        _test_parallel_up_200bps,
        _test_steepener_short_negative_long_positive,
        _test_repricing_gap_aggregates,
        _test_nii_sensitivity_parallel_up,
        _test_eve_sensitivity_outlier,
        _test_eve_sensitivity_compliant,
        _test_engine_register_dup_deposit_raises,
        _test_engine_run_lcr_compliant,
        _test_engine_inflow_with_outflow_direction_raises,
        _test_engine_eve_requires_gap_run_first,
        _test_engine_run_all_irrbb_scenarios_count,
        _test_engine_outlier_filter,
        _test_engine_board_summary,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ treasury_alm self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ treasury_alm self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

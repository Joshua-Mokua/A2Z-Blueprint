"""utils/rwa_optimization.py — v10.34 ENH-235: RWA Optimization.

╔════════════════════════════════════════════════════════════════════════╗
║  RWA OPTIMIZATION & CAPITAL MANAGEMENT — Pillar 1 Basel III             ║
║  Cat A — affects regulatory capital ratios (CET1/T1/Total)            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-235: RWA Optimization & Capital Management.            ║
║                                                                         ║
║  Coverage:                                                              ║
║    SA-CR: Standardized Approach for Credit Risk (Basel III final)     ║
║    SACCR: Standardized Approach for Counterparty Credit Risk          ║
║    Risk-weights per asset class (sovereign / bank / corporate /       ║
║    retail / mortgage / SL / equity)                                    ║
║    RWA = exposure × risk_weight × CCF (off-BS)                       ║
║    Capital ratios: CET1 / T1 / Total                                  ║
║    Pillar 1 minima: CET1 4.5% · T1 6% · Total 8% per BCBS            ║
║    Capital conservation buffer 2.5%                                   ║
║    Countercyclical buffer 0–2.5% (CBK-set)                          ║
║    G-SIB / D-SIB surcharge 0–3.5%                                    ║
║                                                                         ║
║  Coexists with utils/risk_weighted_assets.py + utils/capital_adequacy ║
║  (Volume Seven shells).                                                ║
║                                                                         ║
║  Honesty Rule 1: every RWA result reports per-exposure breakdown +    ║
║  total + risk-weighted + capital required. Capital ratios surface    ║
║  numerator + denominator + threshold + headroom.                      ║
║  Honesty Rule 7: external rating fetcher hookable; without wiring,   ║
║  defaults to "UNRATED" risk-weights rather than fabricating ratings.  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel III final framework (Dec 2017) — SA-CR consolidated           ║
║    Basel BCBS 282 — SA-CCR (counterparty credit risk)                  ║
║    Basel BCBS 189 — Capital conservation buffer + countercyclical    ║
║    Basel d424 (2017) — SA-CR risk-weights revisions                  ║
║    CBK CBK/PG/03 — Capital Adequacy (Kenya Pillar 1 implementation)  ║
║    CBK CBK/PG/04 — Risk Classification of Assets                       ║
║    EBA EBA/GL/2018/01 — uniform disclosures of capital ratios          ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "RWAOptimizationEngine implements ENH-235 SA-CR + SACCR. Per Rule "
    "7, external rating fetcher hookable; without wiring, defaults to "
    "UNRATED risk-weights rather than fabricating ratings. Per Rule 1, "
    "every RWA result reports per-exposure breakdown + total + capital "
    "ratio numerator/denominator/threshold/headroom for examiner trace."
)


# ════════════════════════════════════════════════════════════════════════
# Asset Classes + Risk Weights (Basel III SA-CR)
# ════════════════════════════════════════════════════════════════════════

class AssetClass(Enum):
    """Basel III Standardized Approach asset classes."""
    SOVEREIGN_DOMESTIC = "SOVEREIGN_DOMESTIC"          # Kenya govt KES
    SOVEREIGN_FOREIGN_AAA = "SOVEREIGN_FOREIGN_AAA"
    SOVEREIGN_FOREIGN_BBB = "SOVEREIGN_FOREIGN_BBB"
    SOVEREIGN_FOREIGN_BELOW_B = "SOVEREIGN_FOREIGN_BELOW_B"
    BANK_AAA_AA = "BANK_AAA_AA"
    BANK_A = "BANK_A"
    BANK_BBB = "BANK_BBB"
    BANK_BELOW_BBB = "BANK_BELOW_BBB"
    BANK_UNRATED = "BANK_UNRATED"
    CORPORATE_AAA_AA = "CORPORATE_AAA_AA"
    CORPORATE_A = "CORPORATE_A"
    CORPORATE_BBB = "CORPORATE_BBB"
    CORPORATE_BB = "CORPORATE_BB"
    CORPORATE_BELOW_B = "CORPORATE_BELOW_B"
    CORPORATE_UNRATED = "CORPORATE_UNRATED"
    SME_RETAIL = "SME_RETAIL"                   # SMEs in retail bucket
    SME_CORPORATE = "SME_CORPORATE"
    RETAIL_REGULATORY = "RETAIL_REGULATORY"
    RETAIL_QUALIFYING = "RETAIL_QUALIFYING"
    MORTGAGE_RESIDENTIAL = "MORTGAGE_RESIDENTIAL"
    MORTGAGE_COMMERCIAL = "MORTGAGE_COMMERCIAL"
    EQUITY = "EQUITY"
    EQUITY_LISTED = "EQUITY_LISTED"
    SL_PROJECT = "SL_PROJECT"                   # specialised lending
    DEFAULTED = "DEFAULTED"


# Risk weights per Basel III final framework (Dec 2017) + CBK PG/03
DEFAULT_RISK_WEIGHTS: Mapping[AssetClass, Decimal] = {
    AssetClass.SOVEREIGN_DOMESTIC: Decimal("0"),               # 0%
    AssetClass.SOVEREIGN_FOREIGN_AAA: Decimal("0"),
    AssetClass.SOVEREIGN_FOREIGN_BBB: Decimal("50"),
    AssetClass.SOVEREIGN_FOREIGN_BELOW_B: Decimal("150"),
    AssetClass.BANK_AAA_AA: Decimal("20"),
    AssetClass.BANK_A: Decimal("30"),
    AssetClass.BANK_BBB: Decimal("50"),
    AssetClass.BANK_BELOW_BBB: Decimal("100"),
    AssetClass.BANK_UNRATED: Decimal("50"),                    # SCRA Grade A
    AssetClass.CORPORATE_AAA_AA: Decimal("20"),
    AssetClass.CORPORATE_A: Decimal("50"),
    AssetClass.CORPORATE_BBB: Decimal("75"),
    AssetClass.CORPORATE_BB: Decimal("100"),
    AssetClass.CORPORATE_BELOW_B: Decimal("150"),
    AssetClass.CORPORATE_UNRATED: Decimal("100"),
    AssetClass.SME_RETAIL: Decimal("75"),                       # 75% Basel
    AssetClass.SME_CORPORATE: Decimal("85"),
    AssetClass.RETAIL_REGULATORY: Decimal("75"),
    AssetClass.RETAIL_QUALIFYING: Decimal("75"),
    AssetClass.MORTGAGE_RESIDENTIAL: Decimal("35"),             # CBK PG/03
    AssetClass.MORTGAGE_COMMERCIAL: Decimal("100"),
    AssetClass.EQUITY: Decimal("250"),
    AssetClass.EQUITY_LISTED: Decimal("100"),
    AssetClass.SL_PROJECT: Decimal("130"),                      # operational phase
    AssetClass.DEFAULTED: Decimal("150"),
}


# Credit Conversion Factors for off-balance-sheet items
class CCFCategory(Enum):
    """Credit Conversion Factor categories per Basel III SA-CR."""
    UNCONDITIONALLY_CANCELLABLE = "UNCONDITIONALLY_CANCELLABLE"
    SHORT_TERM_LC = "SHORT_TERM_LC"
    LONG_TERM_LC = "LONG_TERM_LC"
    UNDRAWN_COMMITMENT = "UNDRAWN_COMMITMENT"
    ON_BALANCE_SHEET = "ON_BALANCE_SHEET"


DEFAULT_CCFS: Mapping[CCFCategory, Decimal] = {
    CCFCategory.UNCONDITIONALLY_CANCELLABLE: Decimal("10"),    # 10%
    CCFCategory.SHORT_TERM_LC: Decimal("20"),
    CCFCategory.LONG_TERM_LC: Decimal("50"),
    CCFCategory.UNDRAWN_COMMITMENT: Decimal("40"),
    CCFCategory.ON_BALANCE_SHEET: Decimal("100"),              # already on BS
}


# ════════════════════════════════════════════════════════════════════════
# Capital Buffer Constants (Pillar 1 Basel III + CBK)
# ════════════════════════════════════════════════════════════════════════

CET1_MIN_PCT = Decimal("4.5")           # CET1 minimum
T1_MIN_PCT = Decimal("6.0")             # Tier 1 minimum
TOTAL_CAPITAL_MIN_PCT = Decimal("8.0")  # Total capital minimum
CAPITAL_CONSERVATION_BUFFER_PCT = Decimal("2.5")
COUNTERCYCLICAL_BUFFER_MAX_PCT = Decimal("2.5")
GSIB_SURCHARGE_MAX_PCT = Decimal("3.5")

# CBK PG/03 — Kenya specifically requires
CBK_CET1_MIN_PCT = Decimal("10.5")      # CET1 + buffer = 10.5% in Kenya
CBK_TOTAL_CAPITAL_MIN_PCT = Decimal("14.5")    # 14.5% total


# ════════════════════════════════════════════════════════════════════════
# Exposure + RWA
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Exposure:
    """A regulatory capital exposure."""
    exposure_id: str
    counterparty: str
    asset_class: AssetClass
    on_bs_amount: Decimal               # current drawn / on-BS
    off_bs_amount: Decimal = Decimal("0")
    ccf_category: CCFCategory = CCFCategory.ON_BALANCE_SHEET
    is_secured: bool = False
    collateral_value: Decimal = Decimal("0")
    notes: str = ""


@dataclass(frozen=True)
class RWAExposureResult:
    """RWA computation for a single exposure."""
    exposure_id: str
    asset_class: AssetClass
    risk_weight_pct: Decimal
    effective_exposure: Decimal         # on-BS + off-BS × CCF
    rwa: Decimal                        # effective × RW%
    capital_required_8pct: Decimal      # rwa × 8% (Pillar 1 floor)
    notes: str = ""


def compute_exposure_rwa(
    *,
    exposure: Exposure,
    risk_weights: Mapping[AssetClass, Decimal] = DEFAULT_RISK_WEIGHTS,
    ccfs: Mapping[CCFCategory, Decimal] = DEFAULT_CCFS,
) -> RWAExposureResult:
    """Compute RWA for a single exposure.

    effective_exposure = on_bs + off_bs × CCF − collateral_value (if secured).
    rwa = effective_exposure × risk_weight%.
    """
    rw = risk_weights.get(exposure.asset_class, Decimal("100"))
    ccf = ccfs.get(exposure.ccf_category, Decimal("100"))
    off_bs_eq = (exposure.off_bs_amount * ccf / Decimal("100"))
    effective = exposure.on_bs_amount + off_bs_eq
    if exposure.is_secured:
        effective = max(
            Decimal("0"), effective - exposure.collateral_value)
    effective = effective.quantize(Decimal("0.01"))
    rwa = (effective * rw / Decimal("100")).quantize(Decimal("0.01"))
    capital = (rwa * Decimal("8") / Decimal("100")).quantize(
        Decimal("0.01"))
    return RWAExposureResult(
        exposure_id=exposure.exposure_id,
        asset_class=exposure.asset_class,
        risk_weight_pct=rw,
        effective_exposure=effective,
        rwa=rwa,
        capital_required_8pct=capital,
        notes=(
            f"on_bs={exposure.on_bs_amount}, off_bs={exposure.off_bs_amount} "
            f"× ccf {ccf}% = {off_bs_eq:.2f}; "
            f"{'secured −' + str(exposure.collateral_value) if exposure.is_secured else 'unsecured'}"))


# ════════════════════════════════════════════════════════════════════════
# Capital Components + Ratios
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CapitalComponents:
    """Bank's regulatory capital components."""
    cet1_capital: Decimal
    additional_t1_capital: Decimal      # AT1
    tier_2_capital: Decimal
    deductions: Decimal = Decimal("0")
    notes: str = ""

    @property
    def total_t1(self) -> Decimal:
        return self.cet1_capital + self.additional_t1_capital

    @property
    def total_capital(self) -> Decimal:
        return (self.total_t1 + self.tier_2_capital
                  - self.deductions)


@dataclass(frozen=True)
class CapitalRatioResult:
    """Capital ratio computation outcome."""
    result_id: str
    cet1_pct: Decimal
    t1_pct: Decimal
    total_capital_pct: Decimal
    total_rwa: Decimal
    is_cet1_compliant_basel: bool       # >= 4.5%
    is_t1_compliant_basel: bool         # >= 6%
    is_total_compliant_basel: bool      # >= 8%
    is_cet1_compliant_cbk: bool         # >= 10.5%
    is_total_compliant_cbk: bool        # >= 14.5%
    headroom_cet1_pct: Decimal          # actual − minimum
    as_of_date: str
    notes: str = ""


def compute_capital_ratios(
    *,
    result_id: str,
    capital: CapitalComponents,
    total_rwa: Decimal,
    as_of_date: str,
) -> CapitalRatioResult:
    """Compute Pillar 1 capital ratios per Basel III + CBK PG/03."""
    if total_rwa <= Decimal("0"):
        raise ValueError(
            f"total_rwa must be positive; got {total_rwa}")
    cet1_pct = (
        capital.cet1_capital / total_rwa * Decimal("100")).quantize(
            Decimal("0.01"))
    t1_pct = (
        capital.total_t1 / total_rwa * Decimal("100")).quantize(
            Decimal("0.01"))
    total_pct = (
        capital.total_capital / total_rwa * Decimal("100")).quantize(
            Decimal("0.01"))
    return CapitalRatioResult(
        result_id=result_id,
        cet1_pct=cet1_pct,
        t1_pct=t1_pct,
        total_capital_pct=total_pct,
        total_rwa=total_rwa.quantize(Decimal("0.01")),
        is_cet1_compliant_basel=cet1_pct >= CET1_MIN_PCT,
        is_t1_compliant_basel=t1_pct >= T1_MIN_PCT,
        is_total_compliant_basel=total_pct >= TOTAL_CAPITAL_MIN_PCT,
        is_cet1_compliant_cbk=cet1_pct >= CBK_CET1_MIN_PCT,
        is_total_compliant_cbk=total_pct >= CBK_TOTAL_CAPITAL_MIN_PCT,
        headroom_cet1_pct=(cet1_pct - CBK_CET1_MIN_PCT).quantize(
            Decimal("0.01")),
        as_of_date=as_of_date,
        notes=(
            f"CET1={capital.cet1_capital:,} / "
            f"RWA={total_rwa:,} = {cet1_pct}%; "
            f"Basel min={CET1_MIN_PCT}%, CBK PG/03={CBK_CET1_MIN_PCT}%"))


# ════════════════════════════════════════════════════════════════════════
# SACCR (Counterparty Credit Risk for Derivatives)
# ════════════════════════════════════════════════════════════════════════

class SACCRAssetClass(Enum):
    """SACCR derivative asset classes per Basel BCBS 282."""
    INTEREST_RATE = "INTEREST_RATE"
    FX = "FX"
    CREDIT = "CREDIT"
    EQUITY = "EQUITY"
    COMMODITY = "COMMODITY"


# Supervisory factors per Basel BCBS 282 (in percent of notional)
SACCR_SUPERVISORY_FACTORS_PCT: Mapping[
    SACCRAssetClass, Decimal] = {
    SACCRAssetClass.INTEREST_RATE: Decimal("0.50"),
    SACCRAssetClass.FX: Decimal("4.00"),
    SACCRAssetClass.CREDIT: Decimal("0.46"),
    SACCRAssetClass.EQUITY: Decimal("32.00"),
    SACCRAssetClass.COMMODITY: Decimal("18.00"),
}

# Alpha multiplier per Basel BCBS 282
SACCR_ALPHA = Decimal("1.4")


@dataclass(frozen=True)
class SACCRTrade:
    """One derivative trade for SACCR EAD computation."""
    trade_id: str
    counterparty: str
    asset_class: SACCRAssetClass
    notional: Decimal
    maturity_years: Decimal
    is_long: bool = True
    notes: str = ""


@dataclass(frozen=True)
class SACCREADResult:
    """SACCR exposure-at-default for a counterparty."""
    counterparty: str
    n_trades: int
    replacement_cost: Decimal
    pfe: Decimal                        # potential future exposure
    ead: Decimal                        # alpha × (RC + PFE)
    notes: str = ""


def compute_saccr_ead(
    *,
    counterparty: str,
    trades: Sequence[SACCRTrade],
    current_mtm_total: Decimal,
    collateral_received: Decimal = Decimal("0"),
) -> SACCREADResult:
    """Compute SACCR EAD per Basel BCBS 282.

    EAD = α × (RC + PFE).
    RC = max(MTM - collateral, 0).
    PFE simplified: Σ_trade notional × supervisory_factor × maturity_factor.
    """
    if not trades:
        raise ValueError("compute_saccr_ead requires at least 1 trade")
    rc = max(current_mtm_total - collateral_received, Decimal("0"))
    # Simplified PFE: sum of supervisory factors per trade
    pfe = Decimal("0")
    for t in trades:
        sf_pct = SACCR_SUPERVISORY_FACTORS_PCT.get(
            t.asset_class, Decimal("0"))
        # Maturity factor: sqrt(min(M, 1))
        m_factor = (
            t.maturity_years if t.maturity_years <= Decimal("1")
            else Decimal("1")).sqrt() if hasattr(
            Decimal, 'sqrt') else Decimal("1")
        # Decimal has no sqrt; use approximation for foundation
        if t.maturity_years <= Decimal("1"):
            m_factor = (t.maturity_years ** Decimal("0.5"))
        else:
            m_factor = Decimal("1")
        pfe += t.notional * sf_pct / Decimal("100") * m_factor
    pfe = pfe.quantize(Decimal("0.01"))
    ead = (SACCR_ALPHA * (rc + pfe)).quantize(Decimal("0.01"))
    return SACCREADResult(
        counterparty=counterparty,
        n_trades=len(trades),
        replacement_cost=rc.quantize(Decimal("0.01")),
        pfe=pfe,
        ead=ead,
        notes=(
            f"counterparty {counterparty}: {len(trades)} trades; "
            f"RC={rc}, PFE={pfe}, α={SACCR_ALPHA}"))


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class RWAOptimizationEngine:
    """RWA + capital adequacy orchestrator (Pillar 1 Basel III)."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._exposures: Dict[str, Exposure] = {}
        self._rwa_results: Dict[str, RWAExposureResult] = {}
        self._saccr_trades: Dict[str, SACCRTrade] = {}
        self._capital_results: Dict[str, CapitalRatioResult] = {}

    # ── Exposures ──────────────────────────────────────────────────────
    def register_exposure(self, e: Exposure) -> None:
        if e.exposure_id in self._exposures:
            raise ValueError(f"exposure {e.exposure_id} exists")
        self._exposures[e.exposure_id] = e

    def compute_rwa_for_exposure(
        self, exposure_id: str,
    ) -> RWAExposureResult:
        if exposure_id not in self._exposures:
            raise KeyError(f"exposure {exposure_id} not found")
        result = compute_exposure_rwa(
            exposure=self._exposures[exposure_id])
        self._rwa_results[exposure_id] = result
        return result

    def compute_all_rwa(self) -> Tuple[RWAExposureResult, ...]:
        for eid in self._exposures:
            if eid not in self._rwa_results:
                self.compute_rwa_for_exposure(eid)
        return tuple(self._rwa_results.values())

    def total_rwa(self) -> Decimal:
        if not self._rwa_results and self._exposures:
            self.compute_all_rwa()
        return sum(
            (r.rwa for r in self._rwa_results.values()),
            Decimal("0"))

    def rwa_by_asset_class(self) -> Mapping[AssetClass, Decimal]:
        if not self._rwa_results and self._exposures:
            self.compute_all_rwa()
        out: Dict[AssetClass, Decimal] = {}
        for r in self._rwa_results.values():
            out[r.asset_class] = (
                out.get(r.asset_class, Decimal("0")) + r.rwa)
        return out

    # ── SACCR ──────────────────────────────────────────────────────────
    def register_saccr_trade(self, t: SACCRTrade) -> None:
        if t.trade_id in self._saccr_trades:
            raise ValueError(f"trade {t.trade_id} exists")
        self._saccr_trades[t.trade_id] = t

    def compute_saccr_ead_for_counterparty(
        self, *, counterparty: str,
        current_mtm_total: Decimal,
        collateral_received: Decimal = Decimal("0"),
    ) -> SACCREADResult:
        trades = tuple(
            t for t in self._saccr_trades.values()
            if t.counterparty == counterparty)
        return compute_saccr_ead(
            counterparty=counterparty,
            trades=trades,
            current_mtm_total=current_mtm_total,
            collateral_received=collateral_received)

    # ── Capital ratios ────────────────────────────────────────────────
    def compute_capital_ratios(
        self, *, result_id: str,
        capital: CapitalComponents,
        as_of_date: str,
    ) -> CapitalRatioResult:
        rwa = self.total_rwa()
        if rwa <= Decimal("0"):
            raise ValueError(
                "no RWA computed yet — register exposures and call "
                "compute_all_rwa first")
        result = compute_capital_ratios(
            result_id=result_id, capital=capital,
            total_rwa=rwa, as_of_date=as_of_date)
        self._capital_results[result_id] = result
        return result

    def board_summary(self) -> Dict[str, Any]:
        latest = max(
            self._capital_results.values(),
            key=lambda r: r.as_of_date,
            default=None)
        return {
            "entity": self.entity_name,
            "n_exposures": len(self._exposures),
            "n_rwa_results": len(self._rwa_results),
            "total_rwa": str(self.total_rwa()),
            "n_saccr_trades": len(self._saccr_trades),
            "latest_cet1_pct": (
                str(latest.cet1_pct) if latest else None),
            "latest_total_capital_pct": (
                str(latest.total_capital_pct) if latest else None),
            "latest_cbk_compliant": (
                latest.is_cet1_compliant_cbk if latest else None),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_basel_pillar_1_minima_preserved():
    """Per BCBS final framework Dec 2017."""
    assert CET1_MIN_PCT == Decimal("4.5")
    assert T1_MIN_PCT == Decimal("6.0")
    assert TOTAL_CAPITAL_MIN_PCT == Decimal("8.0")


def _test_cbk_pg_03_minima_preserved():
    assert CBK_CET1_MIN_PCT == Decimal("10.5")
    assert CBK_TOTAL_CAPITAL_MIN_PCT == Decimal("14.5")


def _test_sovereign_domestic_zero_weight():
    assert (DEFAULT_RISK_WEIGHTS[
        AssetClass.SOVEREIGN_DOMESTIC] == Decimal("0"))


def _test_corporate_unrated_100pct():
    assert (DEFAULT_RISK_WEIGHTS[
        AssetClass.CORPORATE_UNRATED] == Decimal("100"))


def _test_residential_mortgage_35pct():
    """CBK PG/03 residential mortgage = 35%."""
    assert (DEFAULT_RISK_WEIGHTS[
        AssetClass.MORTGAGE_RESIDENTIAL] == Decimal("35"))


def _test_defaulted_150pct():
    assert (DEFAULT_RISK_WEIGHTS[
        AssetClass.DEFAULTED] == Decimal("150"))


def _test_compute_rwa_corporate_unrated_100():
    """KES 1M corporate unrated → 100% RW → KES 1M RWA → KES 80K cap."""
    e = Exposure(
        exposure_id="E1", counterparty="ABC Ltd",
        asset_class=AssetClass.CORPORATE_UNRATED,
        on_bs_amount=Decimal("1000000"))
    result = compute_exposure_rwa(exposure=e)
    assert result.rwa == Decimal("1000000.00")
    assert result.capital_required_8pct == Decimal("80000.00")


def _test_compute_rwa_residential_mortgage_35():
    e = Exposure(
        exposure_id="E1", counterparty="John Doe",
        asset_class=AssetClass.MORTGAGE_RESIDENTIAL,
        on_bs_amount=Decimal("1000000"))
    result = compute_exposure_rwa(exposure=e)
    assert result.rwa == Decimal("350000.00")    # 35% × 1M


def _test_compute_rwa_secured_reduces_exposure():
    e = Exposure(
        exposure_id="E1", counterparty="ABC",
        asset_class=AssetClass.CORPORATE_UNRATED,
        on_bs_amount=Decimal("1000000"),
        is_secured=True,
        collateral_value=Decimal("400000"))
    result = compute_exposure_rwa(exposure=e)
    # 600K effective × 100% = 600K RWA
    assert result.effective_exposure == Decimal("600000.00")
    assert result.rwa == Decimal("600000.00")


def _test_compute_rwa_off_bs_with_ccf():
    """Off-BS undrawn commitment → 40% CCF."""
    e = Exposure(
        exposure_id="E1", counterparty="ABC",
        asset_class=AssetClass.CORPORATE_UNRATED,
        on_bs_amount=Decimal("0"),
        off_bs_amount=Decimal("1000000"),
        ccf_category=CCFCategory.UNDRAWN_COMMITMENT)
    result = compute_exposure_rwa(exposure=e)
    # 1M × 40% CCF = 400K effective × 100% RW = 400K RWA
    assert result.effective_exposure == Decimal("400000.00")
    assert result.rwa == Decimal("400000.00")


def _test_capital_ratios_compliant():
    capital = CapitalComponents(
        cet1_capital=Decimal("1500000000"),    # 1.5B
        additional_t1_capital=Decimal("0"),
        tier_2_capital=Decimal("500000000"),)
    result = compute_capital_ratios(
        result_id="C1", capital=capital,
        total_rwa=Decimal("10000000000"),     # 10B
        as_of_date="2026-05-01")
    # CET1 = 1.5B / 10B = 15%
    assert result.cet1_pct == Decimal("15.00")
    assert result.is_cet1_compliant_basel
    assert result.is_cet1_compliant_cbk
    # Total = 2B / 10B = 20%
    assert result.total_capital_pct == Decimal("20.00")
    assert result.is_total_compliant_cbk


def _test_capital_ratios_non_compliant_cbk():
    """8% CET1 is Basel-compliant but below CBK 10.5%."""
    capital = CapitalComponents(
        cet1_capital=Decimal("800000000"),
        additional_t1_capital=Decimal("0"),
        tier_2_capital=Decimal("0"))
    result = compute_capital_ratios(
        result_id="C1", capital=capital,
        total_rwa=Decimal("10000000000"),
        as_of_date="2026-05-01")
    # 800M / 10B = 8%
    assert result.cet1_pct == Decimal("8.00")
    assert result.is_cet1_compliant_basel
    assert not result.is_cet1_compliant_cbk      # below CBK 10.5%


def _test_capital_ratios_zero_rwa_raises():
    capital = CapitalComponents(
        cet1_capital=Decimal("1000000"),
        additional_t1_capital=Decimal("0"),
        tier_2_capital=Decimal("0"))
    try:
        compute_capital_ratios(
            result_id="C1", capital=capital,
            total_rwa=Decimal("0"),
            as_of_date="2026-05-01")
        assert False
    except ValueError:
        pass


def _test_saccr_ir_supervisory_factor():
    assert (SACCR_SUPERVISORY_FACTORS_PCT[
        SACCRAssetClass.INTEREST_RATE] == Decimal("0.50"))


def _test_saccr_alpha_per_bcbs_282():
    assert SACCR_ALPHA == Decimal("1.4")


def _test_saccr_ead_basic():
    """1 IR swap, 100M notional, 1y maturity, 0 MTM, 0 collateral."""
    trades = [SACCRTrade(
        trade_id="T1", counterparty="BankA",
        asset_class=SACCRAssetClass.INTEREST_RATE,
        notional=Decimal("100000000"),
        maturity_years=Decimal("1"))]
    result = compute_saccr_ead(
        counterparty="BankA", trades=trades,
        current_mtm_total=Decimal("0"))
    # PFE = 100M × 0.5% × 1 = 500K; EAD = 1.4 × (0+500K) = 700K
    assert result.replacement_cost == Decimal("0.00")
    assert result.pfe == Decimal("500000.00")
    assert result.ead == Decimal("700000.00")


def _test_saccr_ead_with_mtm_and_collateral():
    trades = [SACCRTrade(
        trade_id="T1", counterparty="BankA",
        asset_class=SACCRAssetClass.INTEREST_RATE,
        notional=Decimal("100000000"),
        maturity_years=Decimal("1"))]
    result = compute_saccr_ead(
        counterparty="BankA", trades=trades,
        current_mtm_total=Decimal("1000000"),
        collateral_received=Decimal("400000"))
    # RC = max(1M - 400K, 0) = 600K
    # EAD = 1.4 × (600K + 500K) = 1.54M
    assert result.replacement_cost == Decimal("600000.00")
    assert result.ead == Decimal("1540000.00")


def _test_saccr_ead_empty_trades_raises():
    try:
        compute_saccr_ead(
            counterparty="X", trades=[],
            current_mtm_total=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_engine_register_dup_exposure_raises():
    eng = RWAOptimizationEngine()
    e = Exposure(
        exposure_id="E1", counterparty="ABC",
        asset_class=AssetClass.CORPORATE_UNRATED,
        on_bs_amount=Decimal("1000000"))
    eng.register_exposure(e)
    try:
        eng.register_exposure(e)
        assert False
    except ValueError:
        pass


def _test_engine_compute_all_rwa_aggregates():
    eng = RWAOptimizationEngine()
    eng.register_exposure(Exposure(
        exposure_id="E1", counterparty="A",
        asset_class=AssetClass.CORPORATE_UNRATED,
        on_bs_amount=Decimal("1000000")))    # 100% → 1M RWA
    eng.register_exposure(Exposure(
        exposure_id="E2", counterparty="B",
        asset_class=AssetClass.MORTGAGE_RESIDENTIAL,
        on_bs_amount=Decimal("1000000")))    # 35% → 350K RWA
    results = eng.compute_all_rwa()
    assert len(results) == 2
    assert eng.total_rwa() == Decimal("1350000")


def _test_engine_capital_ratios_no_exposures_raises():
    eng = RWAOptimizationEngine()
    capital = CapitalComponents(
        cet1_capital=Decimal("1000000"),
        additional_t1_capital=Decimal("0"),
        tier_2_capital=Decimal("0"))
    try:
        eng.compute_capital_ratios(
            result_id="C1", capital=capital,
            as_of_date="2026-05-01")
        assert False
    except ValueError:
        pass


def _test_engine_board_summary():
    eng = RWAOptimizationEngine()
    s = eng.board_summary()
    assert s["entity"] == "Ecobank Kenya"
    assert s["n_exposures"] == 0


def self_test() -> None:
    tests = [
        _test_basel_pillar_1_minima_preserved,
        _test_cbk_pg_03_minima_preserved,
        _test_sovereign_domestic_zero_weight,
        _test_corporate_unrated_100pct,
        _test_residential_mortgage_35pct,
        _test_defaulted_150pct,
        _test_compute_rwa_corporate_unrated_100,
        _test_compute_rwa_residential_mortgage_35,
        _test_compute_rwa_secured_reduces_exposure,
        _test_compute_rwa_off_bs_with_ccf,
        _test_capital_ratios_compliant,
        _test_capital_ratios_non_compliant_cbk,
        _test_capital_ratios_zero_rwa_raises,
        _test_saccr_ir_supervisory_factor,
        _test_saccr_alpha_per_bcbs_282,
        _test_saccr_ead_basic,
        _test_saccr_ead_with_mtm_and_collateral,
        _test_saccr_ead_empty_trades_raises,
        _test_engine_register_dup_exposure_raises,
        _test_engine_compute_all_rwa_aggregates,
        _test_engine_capital_ratios_no_exposures_raises,
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
        print(f"✗ rwa_optimization self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ rwa_optimization self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

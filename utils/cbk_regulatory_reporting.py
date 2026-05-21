"""utils/cbk_regulatory_reporting.py — v10.62: CBK returns.

ENH-252 — CBK Regulatory Reporting Automation (Enhanced).
Cat B — finance arc 4/10.

Diagnostic CBK returns generator. Composes with ENH-248 (general
regulatory reporting framework) but adds banking-specific schedule
templates: CAR, LIQ, SBL, LXP, FXE.

Per Rule 7, engine produces structured returns; never serialises
XBRL/XML/CSV (caller's responsibility); never submits to CBK
portal; never auto-corrects breaches; never modifies balances.

Per Rule 1, every CbkReturnPackage surfaces return_code +
computed_metrics + threshold + threshold_direction + breach_severity
+ inputs_used + framework refs.

Pure stdlib (Decimal + frozen dataclasses + enums).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "CBKRegulatoryReportingEngine implements ENH-252 — "
    "banking-specific returns (CAR/LIQ/SBL/LXP/FXE/NPL/IRR/OPR) extending "
    "ENH-248 framework. Pure stdlib. Per Rule 1, every "
    "CbkReturnPackage surfaces full computed metrics + threshold "
    "+ breach severity + inputs used. Per Rule 7, engine "
    "DIAGNOSTIC ONLY — never serialises, never submits, never "
    "auto-corrects, never modifies balances. CBK thresholds: "
    "CAR≥14.5%, LIQ≥20%, SBL≤25% per borrower, LXP≤800% "
    "aggregate, FXE±10% per currency, NPL≤10% gross ratio, "
    "IRR ΔEVE ≤15% Tier 1, OPR α=15% gross income."
)


class CbkReturnCode(Enum):
    CAR = "CAR"
    LIQ = "LIQ"
    SBL = "SBL"
    LXP = "LXP"
    FXE = "FXE"
    NPL = "NPL"
    IRR = "IRR"
    OPR = "OPR"


class BreachSeverity(Enum):
    NONE = "NONE"
    MARGINAL = "MARGINAL"
    BREACH = "BREACH"
    SEVERE_BREACH = "SEVERE_BREACH"


@dataclass(frozen=True)
class CapitalComponents:
    period: str
    tier1_capital_kes: Decimal
    tier2_capital_kes: Decimal
    deductions_kes: Decimal
    risk_weighted_assets_kes: Decimal

    def __post_init__(self) -> None:
        for f in ("tier1_capital_kes", "tier2_capital_kes",
                  "deductions_kes", "risk_weighted_assets_kes"):
            if getattr(self, f) < 0:
                raise ValueError(f"{f} must be ≥ 0")
        if self.risk_weighted_assets_kes <= 0:
            raise ValueError(
                "risk_weighted_assets_kes must be > 0")


@dataclass(frozen=True)
class LiquidityComponents:
    period: str
    liquid_assets_kes: Decimal
    total_deposits_kes: Decimal

    def __post_init__(self) -> None:
        if self.liquid_assets_kes < 0:
            raise ValueError("liquid_assets_kes must be ≥ 0")
        if self.total_deposits_kes <= 0:
            raise ValueError(
                "total_deposits_kes must be > 0")


@dataclass(frozen=True)
class BorrowerExposure:
    borrower_id: str
    borrower_name: str
    funded_kes: Decimal
    unfunded_kes: Decimal
    is_related_party: bool = False

    def __post_init__(self) -> None:
        if not self.borrower_id:
            raise ValueError("borrower_id must be non-empty")
        if self.funded_kes < 0 or self.unfunded_kes < 0:
            raise ValueError("exposures must be ≥ 0")


@dataclass(frozen=True)
class CurrencyPosition:
    currency: str
    long_kes_equivalent: Decimal
    short_kes_equivalent: Decimal

    def __post_init__(self) -> None:
        if self.currency == "KES":
            raise ValueError("FXE excludes KES")
        if self.long_kes_equivalent < 0:
            raise ValueError("long must be ≥ 0")
        if self.short_kes_equivalent < 0:
            raise ValueError("short must be ≥ 0")


@dataclass(frozen=True)
class NplStaging:
    """Inputs for the NPL classification & provisioning return.

    Per CBK Prudential Guideline PG/04 (Risk Classification of Assets
    and Provisioning) and IFRS 9 staging convention. Stage 3 is the
    NPL pool. Gross loan book = stage 1 + stage 2 + stage 3. The
    threshold this return checks is the Stage 3 share of gross book
    (NPL gross ratio).
    """
    period: str
    stage1_kes: Decimal
    stage2_kes: Decimal
    stage3_kes: Decimal
    stage3_provisions_kes: Decimal

    def __post_init__(self) -> None:
        for f in ("stage1_kes", "stage2_kes", "stage3_kes",
                  "stage3_provisions_kes"):
            if getattr(self, f) < 0:
                raise ValueError(f"{f} must be ≥ 0")
        if (self.stage1_kes + self.stage2_kes
                + self.stage3_kes) <= 0:
            raise ValueError("gross loan book must be > 0")
        if self.stage3_provisions_kes > self.stage3_kes:
            raise ValueError(
                "stage3_provisions_kes cannot exceed stage3_kes")


@dataclass(frozen=True)
class IrrComponents:
    """Inputs for the IRRBB (Interest Rate Risk in Banking Book)
    return — captures the Δ EVE (change in Economic Value of Equity)
    under a parallel ±200bps rate shock, expressed as a percentage of
    Tier 1 capital. Per CBK Prudential Guideline PG/03 §5 and BCBS
    SRP31 (15% supervisory threshold for outlier banks).

    delta_eve_kes is the worst-case (typically the larger absolute
    value of +200bps and -200bps shock results) supplied by the
    caller. Sign convention: a fall in EVE under the shock is a
    positive (bad) value here.
    """
    period: str
    delta_eve_kes: Decimal
    tier1_capital_kes: Decimal
    shock_scenario: str = "PARALLEL_PLUS_MINUS_200BPS"

    def __post_init__(self) -> None:
        if self.delta_eve_kes < 0:
            raise ValueError(
                "delta_eve_kes must be ≥ 0 (absolute worst-case)")
        if self.tier1_capital_kes <= 0:
            raise ValueError(
                "tier1_capital_kes must be > 0")
        if not self.shock_scenario:
            raise ValueError("shock_scenario must be non-empty")


@dataclass(frozen=True)
class OperationalRiskComponents:
    """Inputs for the OPR (Operational Risk Capital Charge) return —
    Basel II Standardised Approach, where the capital requirement is
    α (alpha = 15%) of the 3-year average gross income.

    Per CBK Prudential Guideline PG/03 §6 and BCBS Basel II §649
    (Standardised Approach). The OPR threshold isn't a min/max ratio
    in the same way as CAR; this return classifies whether the
    operational-risk RWA add-on is within reasonable bounds relative
    to total RWA. The default reasonableness threshold is OPR-RWA
    ≤ 25% of total RWA — beyond that flags an unusually high
    operational-risk profile that warrants review.
    """
    period: str
    gross_income_year_minus_2_kes: Decimal
    gross_income_year_minus_1_kes: Decimal
    gross_income_current_year_kes: Decimal
    total_rwa_kes: Decimal

    def __post_init__(self) -> None:
        for f in ("gross_income_year_minus_2_kes",
                  "gross_income_year_minus_1_kes",
                  "gross_income_current_year_kes"):
            # negative gross income years are excluded from the
            # average per Basel II §651 — caller may pass 0 for
            # those years (engine handles the exclusion); negative
            # values are not valid input.
            if getattr(self, f) < 0:
                raise ValueError(f"{f} must be ≥ 0")
        if self.total_rwa_kes <= 0:
            raise ValueError("total_rwa_kes must be > 0")


@dataclass(frozen=True)
class CbkReturnPackage:
    return_code: CbkReturnCode
    period: str
    computed_metrics: Dict[str, Decimal]
    threshold: Decimal
    threshold_direction: str
    breach_severity: BreachSeverity
    breach_description: str
    inputs_used: Dict[str, str]
    framework_refs: Tuple[str, ...]


class CBKRegulatoryReportingEngine:
    CAR_MINIMUM_PCT: Decimal = Decimal("0.145")
    LIQ_MINIMUM_PCT: Decimal = Decimal("0.20")
    SBL_MAXIMUM_PCT: Decimal = Decimal("0.25")
    LXP_AGGREGATE_MAX_MULTIPLE: Decimal = Decimal("8.0")
    FXE_PER_CURRENCY_LIMIT_PCT: Decimal = Decimal("0.10")
    LXP_LARGE_EXPOSURE_THRESHOLD_PCT: Decimal = Decimal("0.10")
    # NPL gross ratio: Stage 3 / gross loan book. CBK PG/04 watch
    # threshold per industry convention; banks above 10% are in
    # supervisory focus. This is a soft guidance line, not a hard
    # cap — calibrated as a "max" for severity classification.
    NPL_RATIO_MAX_PCT: Decimal = Decimal("0.10")
    # IRRBB outlier test: if Δ EVE under ±200bps shock exceeds 15%
    # of Tier 1 capital the bank is flagged as an outlier requiring
    # supervisory review. Per CBK PG/03 §5 + BCBS SRP31.
    IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1: Decimal = Decimal("0.15")
    # Basel II Standardised Approach alpha for operational risk
    # capital charge (15% of 3-year average gross income).
    OPR_ALPHA: Decimal = Decimal("0.15")
    # Reasonableness threshold for operational-risk RWA share of
    # total RWA: above 25% suggests an unusually high op-risk
    # profile that warrants review.
    OPR_RWA_SHARE_MAX_PCT: Decimal = Decimal("0.25")

    @staticmethod
    def _classify_severity(
        actual: Decimal, threshold: Decimal, direction: str,
    ) -> BreachSeverity:
        if direction == "min":
            if actual >= threshold:
                return BreachSeverity.NONE
            shortfall = (threshold - actual) / threshold
            if shortfall <= Decimal("0.10"):
                return BreachSeverity.MARGINAL
            if shortfall >= Decimal("0.25"):
                return BreachSeverity.SEVERE_BREACH
            return BreachSeverity.BREACH
        else:
            if actual <= threshold:
                return BreachSeverity.NONE
            excess = (actual - threshold) / threshold
            if excess <= Decimal("0.10"):
                return BreachSeverity.MARGINAL
            if excess >= Decimal("0.25"):
                return BreachSeverity.SEVERE_BREACH
            return BreachSeverity.BREACH

    def generate_car(
        self, components: CapitalComponents,
    ) -> CbkReturnPackage:
        total_cap = (
            components.tier1_capital_kes
            + components.tier2_capital_kes
            - components.deductions_kes)
        car = (
            total_cap
            / components.risk_weighted_assets_kes).quantize(
            Decimal("0.0001"))
        sev = self._classify_severity(
            car, self.CAR_MINIMUM_PCT, "min")
        return CbkReturnPackage(
            return_code=CbkReturnCode.CAR,
            period=components.period,
            computed_metrics={
                "total_capital_kes": total_cap,
                "rwa_kes": components.risk_weighted_assets_kes,
                "car_ratio": car,
                "car_ratio_pct": (car * 100).quantize(
                    Decimal("0.01"))},
            threshold=self.CAR_MINIMUM_PCT,
            threshold_direction="min",
            breach_severity=sev,
            breach_description=(
                f"CAR {car} vs minimum "
                f"{self.CAR_MINIMUM_PCT} → {sev.value}"),
            inputs_used={
                "tier1": str(components.tier1_capital_kes),
                "tier2": str(components.tier2_capital_kes),
                "deductions": str(components.deductions_kes),
                "rwa": str(
                    components.risk_weighted_assets_kes)},
            framework_refs=(
                "ENH-252 §car",
                "CBK Prudential Guidelines PG 03 §4 — "
                "minimum 14.5% capital adequacy"))

    def generate_liq(
        self, components: LiquidityComponents,
    ) -> CbkReturnPackage:
        ratio = (
            components.liquid_assets_kes
            / components.total_deposits_kes).quantize(
            Decimal("0.0001"))
        sev = self._classify_severity(
            ratio, self.LIQ_MINIMUM_PCT, "min")
        return CbkReturnPackage(
            return_code=CbkReturnCode.LIQ,
            period=components.period,
            computed_metrics={
                "liquid_assets_kes": (
                    components.liquid_assets_kes),
                "total_deposits_kes": (
                    components.total_deposits_kes),
                "liq_ratio": ratio,
                "liq_ratio_pct": (ratio * 100).quantize(
                    Decimal("0.01"))},
            threshold=self.LIQ_MINIMUM_PCT,
            threshold_direction="min",
            breach_severity=sev,
            breach_description=(
                f"LIQ {ratio} vs minimum "
                f"{self.LIQ_MINIMUM_PCT} → {sev.value}"),
            inputs_used={
                "liquid_assets": str(
                    components.liquid_assets_kes),
                "total_deposits": str(
                    components.total_deposits_kes)},
            framework_refs=(
                "ENH-252 §liq",
                "CBK PG 04 — minimum 20% liquidity ratio"))

    def generate_sbl(
        self, period: str, core_capital_kes: Decimal,
        exposures: Sequence[BorrowerExposure],
    ) -> CbkReturnPackage:
        if core_capital_kes <= 0:
            raise ValueError("core_capital must be > 0")
        rows: List[Tuple[str, Decimal, Decimal]] = []
        for ex in exposures:
            total = ex.funded_kes + ex.unfunded_kes
            pct = (total / core_capital_kes).quantize(
                Decimal("0.0001"))
            rows.append((ex.borrower_id, total, pct))
        rows.sort(key=lambda t: t[2], reverse=True)
        top = rows[0] if rows else (
            "NO_EXPOSURES", Decimal("0"), Decimal("0"))
        breaches = [
            r for r in rows if r[2] > self.SBL_MAXIMUM_PCT]
        sev = (
            BreachSeverity.NONE if not rows
            else self._classify_severity(
                top[2], self.SBL_MAXIMUM_PCT, "max"))
        return CbkReturnPackage(
            return_code=CbkReturnCode.SBL,
            period=period,
            computed_metrics={
                "core_capital_kes": core_capital_kes,
                "top_borrower_exposure_kes": top[1],
                "top_borrower_pct_of_core": top[2],
                "borrowers_in_breach": Decimal(len(breaches))},
            threshold=self.SBL_MAXIMUM_PCT,
            threshold_direction="max",
            breach_severity=sev,
            breach_description=(
                f"top borrower {top[0]} at {top[2]} of core "
                f"capital (threshold {self.SBL_MAXIMUM_PCT}); "
                f"{len(breaches)} borrower(s) in breach"),
            inputs_used={
                "core_capital": str(core_capital_kes),
                "borrower_count": str(len(exposures)),
                "breach_count": str(len(breaches))},
            framework_refs=(
                "ENH-252 §sbl",
                "CBK PG 05 — single borrower limit 25% of "
                "core capital"))

    def generate_lxp(
        self, period: str, core_capital_kes: Decimal,
        exposures: Sequence[BorrowerExposure],
    ) -> CbkReturnPackage:
        if core_capital_kes <= 0:
            raise ValueError("core_capital must be > 0")
        large_threshold = (
            core_capital_kes
            * self.LXP_LARGE_EXPOSURE_THRESHOLD_PCT)
        large = [
            ex for ex in exposures
            if ex.funded_kes + ex.unfunded_kes
            > large_threshold]
        agg = sum(
            (ex.funded_kes + ex.unfunded_kes for ex in large),
            Decimal("0"))
        mult = (agg / core_capital_kes).quantize(
            Decimal("0.0001"))
        sev = self._classify_severity(
            mult, self.LXP_AGGREGATE_MAX_MULTIPLE, "max")
        return CbkReturnPackage(
            return_code=CbkReturnCode.LXP,
            period=period,
            computed_metrics={
                "core_capital_kes": core_capital_kes,
                "large_exposure_threshold_kes": large_threshold,
                "large_exposure_count": Decimal(len(large)),
                "aggregate_kes": agg,
                "aggregate_multiple_of_core": mult},
            threshold=self.LXP_AGGREGATE_MAX_MULTIPLE,
            threshold_direction="max",
            breach_severity=sev,
            breach_description=(
                f"{len(large)} large exposure(s) aggregating "
                f"{mult}× core capital (threshold "
                f"{self.LXP_AGGREGATE_MAX_MULTIPLE}×)"),
            inputs_used={
                "core_capital": str(core_capital_kes),
                "all_exposure_count": str(len(exposures))},
            framework_refs=(
                "ENH-252 §lxp",
                "CBK PG 05 — large exposures aggregate ≤ "
                "800% core capital"))

    def generate_fxe(
        self, period: str, core_capital_kes: Decimal,
        positions: Sequence[CurrencyPosition],
    ) -> CbkReturnPackage:
        if core_capital_kes <= 0:
            raise ValueError("core_capital must be > 0")
        worst_cur = ""
        worst_pct = Decimal("0")
        breaches = 0
        per_cur: Dict[str, Decimal] = {}
        for p in positions:
            net = abs(
                p.long_kes_equivalent - p.short_kes_equivalent)
            pct = (net / core_capital_kes).quantize(
                Decimal("0.0001"))
            per_cur[p.currency] = pct
            if pct > self.FXE_PER_CURRENCY_LIMIT_PCT:
                breaches += 1
            if pct > worst_pct:
                worst_pct = pct
                worst_cur = p.currency
        sev = (
            BreachSeverity.NONE if not positions
            else self._classify_severity(
                worst_pct,
                self.FXE_PER_CURRENCY_LIMIT_PCT, "max"))
        return CbkReturnPackage(
            return_code=CbkReturnCode.FXE,
            period=period,
            computed_metrics={
                "core_capital_kes": core_capital_kes,
                "currency_count": Decimal(len(positions)),
                "worst_pct_of_core": worst_pct,
                "currencies_in_breach": Decimal(breaches)},
            threshold=self.FXE_PER_CURRENCY_LIMIT_PCT,
            threshold_direction="max",
            breach_severity=sev,
            breach_description=(
                f"worst currency {worst_cur or 'n/a'} at "
                f"{worst_pct} of core (threshold "
                f"{self.FXE_PER_CURRENCY_LIMIT_PCT}); "
                f"{breaches} currency/ies in breach"),
            inputs_used={
                "core_capital": str(core_capital_kes),
                "currency_count": str(len(positions)),
                **{f"pct_{c}": str(p)
                   for c, p in per_cur.items()}},
            framework_refs=(
                "ENH-252 §fxe",
                "CBK PG 06 — foreign exchange exposure ±10% "
                "per currency of core capital"))

    def generate_npl(
        self, components: NplStaging,
    ) -> CbkReturnPackage:
        """NPL — Non-Performing Loans classification & provisioning.

        Per CBK Prudential Guideline PG/04. The return surfaces the
        gross NPL ratio (Stage 3 / gross loan book) and the
        provision coverage ratio (provisions / Stage 3). The
        threshold check is the gross NPL ratio against the 10%
        watch line; the provision coverage is reported but doesn't
        drive severity (it is informational because adequate
        coverage of a high NPL ratio is still a concern that needs
        the underlying NPL ratio addressed).
        """
        gross_book = (
            components.stage1_kes
            + components.stage2_kes
            + components.stage3_kes)
        npl_ratio = (
            components.stage3_kes / gross_book).quantize(
            Decimal("0.0001"))
        # Coverage: 1 if stage3 is 0; otherwise prov/stage3
        if components.stage3_kes == 0:
            coverage = Decimal("1.0000")
        else:
            coverage = (
                components.stage3_provisions_kes
                / components.stage3_kes).quantize(
                Decimal("0.0001"))
        sev = self._classify_severity(
            npl_ratio, self.NPL_RATIO_MAX_PCT, "max")
        return CbkReturnPackage(
            return_code=CbkReturnCode.NPL,
            period=components.period,
            computed_metrics={
                "gross_loan_book_kes": gross_book,
                "stage3_kes": components.stage3_kes,
                "npl_ratio": npl_ratio,
                "npl_ratio_pct": (npl_ratio * 100).quantize(
                    Decimal("0.01")),
                "stage3_provisions_kes": (
                    components.stage3_provisions_kes),
                "provision_coverage_ratio": coverage,
                "provision_coverage_pct": (
                    coverage * 100).quantize(Decimal("0.01"))},
            threshold=self.NPL_RATIO_MAX_PCT,
            threshold_direction="max",
            breach_severity=sev,
            breach_description=(
                f"NPL ratio {npl_ratio} vs max "
                f"{self.NPL_RATIO_MAX_PCT} → {sev.value}; "
                f"provision coverage {coverage}"),
            inputs_used={
                "stage1": str(components.stage1_kes),
                "stage2": str(components.stage2_kes),
                "stage3": str(components.stage3_kes),
                "stage3_provisions": str(
                    components.stage3_provisions_kes)},
            framework_refs=(
                "ENH-252 §npl",
                "CBK Prudential Guidelines PG 04 — risk "
                "classification of assets and provisioning",
                "IFRS 9 staging convention"))

    def generate_irr(
        self, components: IrrComponents,
    ) -> CbkReturnPackage:
        """IRR — Interest Rate Risk in the Banking Book.

        Per CBK Prudential Guideline PG/03 §5 + BCBS SRP31. The
        return surfaces Δ EVE under a parallel ±200bps rate shock
        as a percentage of Tier 1 capital. Threshold is the 15%
        outlier line — banks above this threshold are classified
        as outliers and subject to supervisory review.
        """
        eve_share = (
            components.delta_eve_kes
            / components.tier1_capital_kes).quantize(
            Decimal("0.0001"))
        sev = self._classify_severity(
            eve_share, self.IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1,
            "max")
        return CbkReturnPackage(
            return_code=CbkReturnCode.IRR,
            period=components.period,
            computed_metrics={
                "delta_eve_kes": components.delta_eve_kes,
                "tier1_capital_kes": (
                    components.tier1_capital_kes),
                "delta_eve_share_of_tier1": eve_share,
                "delta_eve_pct_of_tier1": (
                    eve_share * 100).quantize(Decimal("0.01"))},
            threshold=self.IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1,
            threshold_direction="max",
            breach_severity=sev,
            breach_description=(
                f"Δ EVE / Tier 1 = {eve_share} vs max "
                f"{self.IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1} → "
                f"{sev.value} (shock: {components.shock_scenario})"),
            inputs_used={
                "delta_eve_kes": str(components.delta_eve_kes),
                "tier1_capital_kes": str(
                    components.tier1_capital_kes),
                "shock_scenario": components.shock_scenario},
            framework_refs=(
                "ENH-252 §irr",
                "CBK Prudential Guidelines PG 03 §5 — IRRBB",
                "BCBS SRP31 — outlier test 15% of Tier 1"))

    def generate_opr(
        self, components: OperationalRiskComponents,
    ) -> CbkReturnPackage:
        """OPR — Operational Risk Capital Charge.

        Basel II Standardised Approach: the operational-risk
        capital requirement is α (alpha = 15%) × 3-year average
        gross income, with negative-income years excluded from the
        denominator per Basel II §651. The implied OPR-RWA is the
        capital charge × 12.5 (the inverse of the 8% minimum
        capital ratio). Severity is classified against the OPR-RWA
        share of total RWA — above 25% is unusual and flagged.

        Per CBK Prudential Guideline PG/03 §6 + BCBS Basel II §649.
        """
        years = [
            components.gross_income_year_minus_2_kes,
            components.gross_income_year_minus_1_kes,
            components.gross_income_current_year_kes,
        ]
        positive_years = [y for y in years if y > 0]
        if not positive_years:
            avg_gross_income = Decimal("0")
        else:
            avg_gross_income = (
                sum(positive_years)
                / Decimal(len(positive_years))).quantize(
                Decimal("0.01"))
        capital_charge = (
            self.OPR_ALPHA * avg_gross_income).quantize(
            Decimal("0.01"))
        opr_rwa = (capital_charge * Decimal("12.5")).quantize(
            Decimal("0.01"))
        opr_share = (
            opr_rwa / components.total_rwa_kes).quantize(
            Decimal("0.0001"))
        sev = self._classify_severity(
            opr_share, self.OPR_RWA_SHARE_MAX_PCT, "max")
        return CbkReturnPackage(
            return_code=CbkReturnCode.OPR,
            period=components.period,
            computed_metrics={
                "avg_gross_income_kes": avg_gross_income,
                "capital_charge_kes": capital_charge,
                "implied_opr_rwa_kes": opr_rwa,
                "total_rwa_kes": components.total_rwa_kes,
                "opr_rwa_share": opr_share,
                "opr_rwa_share_pct": (
                    opr_share * 100).quantize(Decimal("0.01")),
                "positive_years_count": Decimal(
                    len(positive_years))},
            threshold=self.OPR_RWA_SHARE_MAX_PCT,
            threshold_direction="max",
            breach_severity=sev,
            breach_description=(
                f"OPR-RWA share {opr_share} vs max "
                f"{self.OPR_RWA_SHARE_MAX_PCT} → {sev.value} "
                f"(α={self.OPR_ALPHA} × 3-yr avg gross income, "
                f"{len(positive_years)} positive years)"),
            inputs_used={
                "gross_income_y-2": str(
                    components.gross_income_year_minus_2_kes),
                "gross_income_y-1": str(
                    components.gross_income_year_minus_1_kes),
                "gross_income_current": str(
                    components.gross_income_current_year_kes),
                "total_rwa": str(components.total_rwa_kes)},
            framework_refs=(
                "ENH-252 §opr",
                "CBK Prudential Guidelines PG 03 §6 — operational risk",
                "BCBS Basel II §649 — Standardised Approach α=15%"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_capital_validates_negative():
    try:
        CapitalComponents(
            period="2026-04",
            tier1_capital_kes=Decimal("-1"),
            tier2_capital_kes=Decimal("0"),
            deductions_kes=Decimal("0"),
            risk_weighted_assets_kes=Decimal("100"))
        assert False
    except ValueError:
        pass


def _test_capital_validates_zero_rwa():
    try:
        CapitalComponents(
            period="2026-04",
            tier1_capital_kes=Decimal("100"),
            tier2_capital_kes=Decimal("0"),
            deductions_kes=Decimal("0"),
            risk_weighted_assets_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_liq_validates_zero_deposits():
    try:
        LiquidityComponents(
            period="2026-04",
            liquid_assets_kes=Decimal("100"),
            total_deposits_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_currency_position_rejects_kes():
    try:
        CurrencyPosition(
            currency="KES",
            long_kes_equivalent=Decimal("100"),
            short_kes_equivalent=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_borrower_exposure_validates_id():
    try:
        BorrowerExposure(
            borrower_id="", borrower_name="X",
            funded_kes=Decimal("1"),
            unfunded_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_car_passing():
    eng = CBKRegulatoryReportingEngine()
    comp = CapitalComponents(
        period="2026-04",
        tier1_capital_kes=Decimal("1000000000"),
        tier2_capital_kes=Decimal("200000000"),
        deductions_kes=Decimal("100000000"),
        risk_weighted_assets_kes=Decimal("5000000000"))
    pkg = eng.generate_car(comp)
    assert pkg.return_code == CbkReturnCode.CAR
    assert pkg.breach_severity == BreachSeverity.NONE
    assert pkg.computed_metrics["car_ratio"] == Decimal("0.22")


def _test_car_breach_severe():
    eng = CBKRegulatoryReportingEngine()
    comp = CapitalComponents(
        period="2026-04",
        tier1_capital_kes=Decimal("100000000"),
        tier2_capital_kes=Decimal("0"),
        deductions_kes=Decimal("0"),
        risk_weighted_assets_kes=Decimal("5000000000"))
    pkg = eng.generate_car(comp)
    # 100m / 5bn = 2% — severely below 14.5%
    assert pkg.breach_severity == BreachSeverity.SEVERE_BREACH


def _test_liq_passing():
    eng = CBKRegulatoryReportingEngine()
    comp = LiquidityComponents(
        period="2026-04",
        liquid_assets_kes=Decimal("3000000000"),
        total_deposits_kes=Decimal("10000000000"))
    pkg = eng.generate_liq(comp)
    assert pkg.breach_severity == BreachSeverity.NONE
    assert pkg.computed_metrics["liq_ratio"] == Decimal("0.30")


def _test_liq_breach():
    eng = CBKRegulatoryReportingEngine()
    comp = LiquidityComponents(
        period="2026-04",
        liquid_assets_kes=Decimal("1500000000"),
        total_deposits_kes=Decimal("10000000000"))
    pkg = eng.generate_liq(comp)
    # 15% — 25% below 20% threshold → SEVERE
    assert pkg.breach_severity == BreachSeverity.SEVERE_BREACH


def _test_sbl_passing():
    eng = CBKRegulatoryReportingEngine()
    exposures = (
        BorrowerExposure(
            borrower_id="B1", borrower_name="Borrower One",
            funded_kes=Decimal("100000000"),
            unfunded_kes=Decimal("20000000")),
        BorrowerExposure(
            borrower_id="B2", borrower_name="Borrower Two",
            funded_kes=Decimal("50000000"),
            unfunded_kes=Decimal("10000000")),
    )
    pkg = eng.generate_sbl(
        "2026-04", Decimal("1000000000"), exposures)
    # Top: B1 at 120m / 1bn = 12% < 25% threshold
    assert pkg.breach_severity == BreachSeverity.NONE
    assert pkg.computed_metrics[
        "top_borrower_pct_of_core"] == Decimal("0.12")


def _test_sbl_breach():
    eng = CBKRegulatoryReportingEngine()
    exposures = (
        BorrowerExposure(
            borrower_id="BIG", borrower_name="Big Borrower",
            funded_kes=Decimal("400000000"),
            unfunded_kes=Decimal("50000000")),
    )
    pkg = eng.generate_sbl(
        "2026-04", Decimal("1000000000"), exposures)
    # 450m / 1bn = 45% > 25% threshold by 80% → SEVERE
    assert pkg.breach_severity == BreachSeverity.SEVERE_BREACH
    assert pkg.computed_metrics["borrowers_in_breach"] == (
        Decimal("1"))


def _test_lxp_passing():
    eng = CBKRegulatoryReportingEngine()
    # Large = >10% of core (1bn × 10% = 100m)
    exposures = (
        BorrowerExposure(
            borrower_id="L1", borrower_name="L1",
            funded_kes=Decimal("150000000"),
            unfunded_kes=Decimal("0")),
        BorrowerExposure(
            borrower_id="S1", borrower_name="Small",
            funded_kes=Decimal("50000000"),
            unfunded_kes=Decimal("0")),
    )
    pkg = eng.generate_lxp(
        "2026-04", Decimal("1000000000"), exposures)
    # 1 large at 150m → aggregate 0.15× core, well below 8×
    assert pkg.breach_severity == BreachSeverity.NONE
    assert pkg.computed_metrics["large_exposure_count"] == (
        Decimal("1"))


def _test_fxe_within_limits():
    eng = CBKRegulatoryReportingEngine()
    positions = (
        CurrencyPosition(
            currency="USD",
            long_kes_equivalent=Decimal("80000000"),
            short_kes_equivalent=Decimal("30000000")),
        CurrencyPosition(
            currency="EUR",
            long_kes_equivalent=Decimal("20000000"),
            short_kes_equivalent=Decimal("10000000")),
    )
    pkg = eng.generate_fxe(
        "2026-04", Decimal("1000000000"), positions)
    # USD net 50m / 1bn = 5% < 10%; EUR net 10m / 1bn = 1%
    assert pkg.breach_severity == BreachSeverity.NONE


def _test_fxe_breach():
    eng = CBKRegulatoryReportingEngine()
    positions = (
        CurrencyPosition(
            currency="USD",
            long_kes_equivalent=Decimal("200000000"),
            short_kes_equivalent=Decimal("0")),
    )
    pkg = eng.generate_fxe(
        "2026-04", Decimal("1000000000"), positions)
    # 20% > 10% by 100% → SEVERE
    assert pkg.breach_severity == BreachSeverity.SEVERE_BREACH


def _test_provenance_full():
    eng = CBKRegulatoryReportingEngine()
    comp = CapitalComponents(
        period="2026-04",
        tier1_capital_kes=Decimal("500000000"),
        tier2_capital_kes=Decimal("100000000"),
        deductions_kes=Decimal("50000000"),
        risk_weighted_assets_kes=Decimal("4000000000"))
    pkg = eng.generate_car(comp)
    assert "tier1" in pkg.inputs_used
    assert "rwa" in pkg.inputs_used
    assert any("ENH-252" in r for r in pkg.framework_refs)
    assert any("CBK" in r for r in pkg.framework_refs)


def _test_engine_does_not_mutate_inputs():
    eng = CBKRegulatoryReportingEngine()
    comp = CapitalComponents(
        period="2026-04",
        tier1_capital_kes=Decimal("1000000000"),
        tier2_capital_kes=Decimal("0"),
        deductions_kes=Decimal("0"),
        risk_weighted_assets_kes=Decimal("5000000000"))
    eng.generate_car(comp)
    assert comp.tier1_capital_kes == Decimal("1000000000")


def _test_marginal_severity_classification():
    eng = CBKRegulatoryReportingEngine()
    # CAR at 13.5% — shortfall 1%/14.5% = 6.9% → MARGINAL
    comp = CapitalComponents(
        period="2026-04",
        tier1_capital_kes=Decimal("675000000"),
        tier2_capital_kes=Decimal("0"),
        deductions_kes=Decimal("0"),
        risk_weighted_assets_kes=Decimal("5000000000"))
    pkg = eng.generate_car(comp)
    # 675m / 5bn = 13.5%
    assert pkg.computed_metrics["car_ratio"] == Decimal("0.135")
    assert pkg.breach_severity == BreachSeverity.MARGINAL


def _test_npl_passing():
    """NPL at 8% gross ratio is below 10% watch line → NONE."""
    eng = CBKRegulatoryReportingEngine()
    comp = NplStaging(
        period="2026Q1",
        stage1_kes=Decimal("80_000_000_000"),
        stage2_kes=Decimal("12_000_000_000"),
        stage3_kes=Decimal("8_000_000_000"),
        stage3_provisions_kes=Decimal("3_500_000_000"))
    pkg = eng.generate_npl(comp)
    assert pkg.return_code == CbkReturnCode.NPL
    assert pkg.computed_metrics["npl_ratio"] == Decimal("0.08")
    assert pkg.breach_severity == BreachSeverity.NONE


def _test_npl_breach():
    """NPL at 15% gross ratio → severe breach."""
    eng = CBKRegulatoryReportingEngine()
    comp = NplStaging(
        period="2026Q1",
        stage1_kes=Decimal("70_000_000_000"),
        stage2_kes=Decimal("15_000_000_000"),
        stage3_kes=Decimal("15_000_000_000"),
        stage3_provisions_kes=Decimal("6_000_000_000"))
    pkg = eng.generate_npl(comp)
    assert pkg.computed_metrics["npl_ratio"] == Decimal("0.15")
    assert pkg.breach_severity == BreachSeverity.SEVERE_BREACH
    # Coverage 6/15 = 40%
    assert pkg.computed_metrics["provision_coverage_ratio"] == Decimal("0.4")


def _test_npl_validates_provisions_exceed_stage3():
    """Provisions cannot exceed Stage 3 balance."""
    try:
        NplStaging(
            period="2026Q1",
            stage1_kes=Decimal("100"),
            stage2_kes=Decimal("0"),
            stage3_kes=Decimal("10"),
            stage3_provisions_kes=Decimal("20"))
    except ValueError:
        return
    raise AssertionError(
        "expected ValueError when provisions exceed Stage 3")


def _test_irr_passing():
    """Δ EVE 2B vs Tier 1 25B = 8% — below 15% outlier line."""
    eng = CBKRegulatoryReportingEngine()
    comp = IrrComponents(
        period="2026Q1",
        delta_eve_kes=Decimal("2_000_000_000"),
        tier1_capital_kes=Decimal("25_000_000_000"))
    pkg = eng.generate_irr(comp)
    assert pkg.return_code == CbkReturnCode.IRR
    assert pkg.computed_metrics["delta_eve_share_of_tier1"] == Decimal("0.08")
    assert pkg.breach_severity == BreachSeverity.NONE


def _test_irr_breach():
    """Δ EVE 7B vs Tier 1 25B = 28% — severe breach."""
    eng = CBKRegulatoryReportingEngine()
    comp = IrrComponents(
        period="2026Q1",
        delta_eve_kes=Decimal("7_000_000_000"),
        tier1_capital_kes=Decimal("25_000_000_000"))
    pkg = eng.generate_irr(comp)
    assert pkg.computed_metrics["delta_eve_share_of_tier1"] == Decimal("0.28")
    assert pkg.breach_severity == BreachSeverity.SEVERE_BREACH


def _test_opr_passing():
    """OPR-RWA 22.5% of total RWA — below 25% reasonableness line."""
    eng = CBKRegulatoryReportingEngine()
    comp = OperationalRiskComponents(
        period="2026Q1",
        gross_income_year_minus_2_kes=Decimal("11_000_000_000"),
        gross_income_year_minus_1_kes=Decimal("12_500_000_000"),
        gross_income_current_year_kes=Decimal("12_500_000_000"),
        total_rwa_kes=Decimal("100_000_000_000"))
    pkg = eng.generate_opr(comp)
    assert pkg.return_code == CbkReturnCode.OPR
    # 3-yr avg = 12B; charge = 0.15 × 12B = 1.8B; RWA = 1.8B × 12.5 = 22.5B
    assert pkg.computed_metrics["capital_charge_kes"] == Decimal("1800000000.00")
    assert pkg.computed_metrics["implied_opr_rwa_kes"] == Decimal("22500000000.00")
    assert pkg.breach_severity == BreachSeverity.NONE


def _test_opr_excludes_negative_year():
    """Per Basel II §651, negative gross-income years are excluded
    from the 3-year average. The engine here treats 0 as exclusion
    (the dataclass rejects negative values). With only 2 positive
    years, the average uses 2 not 3 in the denominator."""
    eng = CBKRegulatoryReportingEngine()
    comp = OperationalRiskComponents(
        period="2026Q1",
        gross_income_year_minus_2_kes=Decimal("0"),  # crisis year
        gross_income_year_minus_1_kes=Decimal("10_000_000_000"),
        gross_income_current_year_kes=Decimal("12_000_000_000"),
        total_rwa_kes=Decimal("100_000_000_000"))
    pkg = eng.generate_opr(comp)
    # avg = 22B/2 = 11B (not 7.33B which would average over 3 years)
    assert pkg.computed_metrics["avg_gross_income_kes"] == Decimal("11000000000.00")
    assert pkg.computed_metrics["positive_years_count"] == Decimal("2")


# ─────────────────────────────────────────────────────────────────────
# v10.265 — Persistence helper for generated CbkReturnPackage objects.
#
# Per the v10.262/v10.263/v10.264 honest acknowledgements, the 9 UI
# tabs (4 BSD + 5 Risk-Based) compute + display + audit-log but do
# NOT persist the package. This helper provides the save path:
# 1. Convert package to dict (Decimal/Enum to strings)
# 2. Append to data/cbk_returns_generated.json (dual_save-compatible)
# 3. Optional PG insert if A2Z_USE_DB=true
#
# v10.266 will wire calls to this helper in each generation tab.
# ─────────────────────────────────────────────────────────────────────


def package_to_persist_dict(
    pkg: "CbkReturnPackage",
    generated_by: str,
) -> Dict[str, Any]:
    """Serialize a CbkReturnPackage to a dict suitable for JSON
    storage AND PostgreSQL INSERT (matching the v10.265 DDL).

    The id is synthesized as <return_code>_<period>_<utc_timestamp>
    for natural traceability without requiring UUID generation.
    """
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    pid = (
        f"{pkg.return_code.value}_"
        f"{pkg.period}_"
        f"{now.strftime('%Y%m%dT%H%M%S')}"
    )
    return {
        "id": pid,
        "return_code": pkg.return_code.value,
        "period": pkg.period,
        "generated_at": now.isoformat(),
        "generated_by": generated_by,
        "breach_severity": pkg.breach_severity.value,
        "threshold": str(pkg.threshold),
        "threshold_direction": pkg.threshold_direction,
        "breach_description": pkg.breach_description,
        "computed_metrics": {
            k: str(v) for k, v in pkg.computed_metrics.items()
        },
        "inputs_used": dict(pkg.inputs_used),
        "framework_refs": list(pkg.framework_refs),
    }


def save_cbk_package(
    pkg: "CbkReturnPackage",
    generated_by: str,
    data_dir: Optional[Any] = None,
) -> Dict[str, Any]:
    """Save a generated CbkReturnPackage to JSON (always) + PG
    (when A2Z_USE_DB is enabled). Returns the persisted dict.

    Append-only: each generation creates a new row. History is
    preserved for period-over-period analysis.

    Uses utils.db.dual_save() which:
      - Always writes the full updated list to JSON (atomic)
      - Conditionally upserts to PG when the table is migrated
      - Centralizes I/O so callers don't trip G2 direct_io gate

    Caller is responsible for passing `data_dir` (typically the page's
    DATA path constant). If None, defaults to repo's data/ folder.
    """
    from pathlib import Path as _Path

    persist_dict = package_to_persist_dict(pkg, generated_by)

    # Determine target JSON path
    if data_dir is None:
        # Default to project's data/ folder relative to this module
        data_dir = _Path(__file__).parent.parent / "data"
    json_path = _Path(data_dir) / "cbk_returns_generated.json"

    # Read existing rows via dual_load (centralized I/O)
    try:
        from utils.db import db as _db   # singleton Database instance, not module
        existing = _db.dual_load(
            json_path,
            table="cbk_returns_generated",
            index_cols=("id",))
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
    existing.append(persist_dict)

    # Write via dual_save (centralized I/O — JSON always, PG when migrated)
    pg_persisted = False
    try:
        from utils.db import db as _db   # singleton Database instance
        ok = _db.dual_save(
            json_path,
            data=existing,
            table="cbk_returns_generated",
            pk_col="id",
            flat_cols=("id", "return_code", "period",
                        "generated_at", "generated_by",
                        "breach_severity", "threshold",
                        "threshold_direction", "breach_description"))
        # dual_save handles PG write internally based on table migration state
        # We can't directly observe pg_persisted from its return value;
        # treat True return as best-effort persistence
        pg_persisted = bool(ok)
    except Exception as e:
        return {
            "persisted": False,
            "error": str(e),
            "data": persist_dict,
        }

    return {
        "persisted": True,
        "pg_persisted": pg_persisted,
        "data": persist_dict,
    }


def save_bsd_result(
    bsd_result: Dict[str, Any],
    return_code: str,
    period: str,
    generated_by: str,
    data_dir: Optional[Any] = None,
) -> Dict[str, Any]:
    """Save a BSD generator result dict to JSON (always) + PG (when
    A2Z_USE_DB is enabled). Adapter that maps BSD dict → same
    persist_dict shape as save_cbk_package, so both flows write to
    the same cbk_returns_generated table.

    BSD generators in utils/regulatory_returns.py return Dict[str, Any]
    rather than CbkReturnPackage. Common fields:
      - return_type: "BSD_1" | "BSD_2" | "BSD_3" | "BSD_17"
      - generated: bool
      - compliant: bool | None
      - validation_errors: list[str] (when generated=False)
      - Plus return-specific fields (liquidity_ratio_pct, npl_ratio_pct,
        cet1_ratio_pct, balance_check, etc.)

    Mapping to persist_dict:
      - return_code: passed in as parameter (e.g. "BSD-1")
      - period: passed in (e.g. reporting_date.isoformat()[:7])
      - breach_severity: derived from compliant flag
        (True → NONE, False → BREACH, None → NONE)
      - computed_metrics: full BSD result dict (as JSONB)
      - inputs_used: empty dict (BSD inputs already audit-logged
        separately)
      - framework_refs: ("Standard #80",
                         "{regulator()} BSD return suite")
      - threshold + threshold_direction: omitted (BSDs don't use
        the same single-threshold model as the risk-based packages)

    Same dual_save plumbing as save_cbk_package, same append-only
    history.
    """
    from pathlib import Path as _Path
    import datetime as _dt

    # Synthesize id matching save_cbk_package convention
    _ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    _id = f"{return_code}_{period}_{_ts}"

    # Derive severity from compliant flag (BSD's binary success signal)
    _compliant = bsd_result.get("compliant")
    if _compliant is True:
        _severity = "NONE"
        _description = (
            f"{return_code} compliant for period {period}")
    elif _compliant is False:
        _severity = "BREACH"
        _description = (
            f"{return_code} breach detected for period "
            f"{period} — review {return_code} tab output")
    else:
        # generated=False or compliant=None
        _severity = "NONE"
        _description = (
            f"{return_code} generated for period {period} "
            f"(compliance flag not applicable or generation "
            f"incomplete)")

    persist_dict = {
        "id": _id,
        "return_code": return_code,
        "period": period,
        "generated_at": (
            _dt.datetime.now(_dt.timezone.utc).isoformat()),
        "generated_by": generated_by,
        "breach_severity": _severity,
        "threshold": None,
        "threshold_direction": None,
        "breach_description": _description,
        "computed_metrics": {
            k: str(v) for k, v in bsd_result.items()
            if not isinstance(v, (dict, list))
        },
        "inputs_used": {},
        "framework_refs": [
            "Standard #80",
            "BSD return suite — daily/weekly/monthly cadence",
        ],
    }

    # Determine target JSON path
    if data_dir is None:
        data_dir = _Path(__file__).parent.parent / "data"
    json_path = _Path(data_dir) / "cbk_returns_generated.json"

    # Read existing rows via dual_load (same singleton pattern as save_cbk_package)
    try:
        from utils.db import db as _db
        existing = _db.dual_load(
            json_path,
            table="cbk_returns_generated",
            index_cols=("id",))
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
    existing.append(persist_dict)

    # Write via dual_save
    pg_persisted = False
    try:
        from utils.db import db as _db
        ok = _db.dual_save(
            json_path,
            data=existing,
            table="cbk_returns_generated",
            pk_col="id",
            flat_cols=("id", "return_code", "period",
                        "generated_at", "generated_by",
                        "breach_severity", "threshold",
                        "threshold_direction", "breach_description"))
        pg_persisted = bool(ok)
    except Exception as e:
        return {
            "persisted": False,
            "error": str(e),
            "data": persist_dict,
        }

    return {
        "persisted": True,
        "pg_persisted": pg_persisted,
        "data": persist_dict,
    }


def _test_save_cbk_package_serialization():
    """Smoke test for v10.265: package_to_persist_dict produces a
    dict with the right shape (no Decimals or Enums leak out)."""
    engine = CBKRegulatoryReportingEngine()
    pkg = engine.generate_sbl(
        period="2026-04",
        core_capital_kes=Decimal("15000000000"),
        exposures=[
            BorrowerExposure(
                "B001", "Test Borrower",
                Decimal("1000000000"), Decimal("100000000")),
        ])
    persist = package_to_persist_dict(pkg, generated_by="test_user")
    # All values must be JSON-serializable primitives
    for k, v in persist.items():
        assert not isinstance(v, Decimal), (
            f"{k} leaked Decimal: {v}")
    assert persist["return_code"] == "SBL"
    assert persist["generated_by"] == "test_user"
    assert persist["breach_severity"] in (
        "NONE", "MARGINAL", "BREACH", "SEVERE_BREACH")
    assert persist["id"].startswith("SBL_2026-04_")
    # JSON round-trip must succeed
    s = json.dumps(persist)
    assert json.loads(s) == persist


def self_test() -> None:
    tests = [
        _test_capital_validates_negative,
        _test_capital_validates_zero_rwa,
        _test_liq_validates_zero_deposits,
        _test_currency_position_rejects_kes,
        _test_borrower_exposure_validates_id,
        _test_car_passing,
        _test_car_breach_severe,
        _test_liq_passing,
        _test_liq_breach,
        _test_sbl_passing,
        _test_sbl_breach,
        _test_lxp_passing,
        _test_fxe_within_limits,
        _test_fxe_breach,
        _test_provenance_full,
        _test_engine_does_not_mutate_inputs,
        _test_marginal_severity_classification,
        _test_npl_passing,
        _test_npl_breach,
        _test_npl_validates_provisions_exceed_stage3,
        _test_irr_passing,
        _test_irr_breach,
        _test_opr_passing,
        _test_opr_excludes_negative_year,
        _test_save_cbk_package_serialization,
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
        print(
            f"✗ cbk_regulatory_reporting self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ cbk_regulatory_reporting self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

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

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "CBKRegulatoryReportingEngine implements ENH-252 — "
    "banking-specific returns (CAR/LIQ/SBL/LXP/FXE) extending "
    "ENH-248 framework. Pure stdlib. Per Rule 1, every "
    "CbkReturnPackage surfaces full computed metrics + threshold "
    "+ breach severity + inputs used. Per Rule 7, engine "
    "DIAGNOSTIC ONLY — never serialises, never submits, never "
    "auto-corrects, never modifies balances. CBK thresholds: "
    "CAR≥14.5%, LIQ≥20%, SBL≤25% per borrower, LXP≤800% "
    "aggregate, FXE±10% per currency."
)


class CbkReturnCode(Enum):
    CAR = "CAR"
    LIQ = "LIQ"
    SBL = "SBL"
    LXP = "LXP"
    FXE = "FXE"


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

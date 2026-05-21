"""utils/op_risk.py — v10.43: Operational Risk SMA Framework.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-OR-001 — SMA Operational Risk Capital                              ║
║  Cat A — Risk arc continuation                                          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Replaces AMA / BIA / TSA per BCBS d457 (Dec 2017, effective Jan 2023). ║
║                                                                          ║
║  Three components:                                                       ║
║    BI  = Business Indicator (3-year average)                             ║
║         = ILDC + SC + FC                                                 ║
║      ILDC = min(|II−IE|, 0.0225×IEA) + DI                                ║
║             (interest, lease, dividend component)                        ║
║      SC   = max(OI, OE) + max(FI, FE)                                    ║
║             (services component)                                         ║
║      FC   = |Net P&L Trading Book| + |Net P&L Banking Book|              ║
║             (financial component)                                        ║
║                                                                          ║
║    BIC = Business Indicator Component                                    ║
║         = bucket-wise marginal α applied to BI                           ║
║      Bucket 1: BI ≤ 1bn EUR              → α₁ = 12%                      ║
║      Bucket 2: 1bn < BI ≤ 30bn EUR       → α₂ = 15% (above 1bn)          ║
║      Bucket 3: BI > 30bn EUR             → α₃ = 18% (above 30bn)         ║
║                                                                          ║
║    ILM = Internal Loss Multiplier                                        ║
║         = ln(exp(1) − 1 + (LC/BIC)^0.8)                                  ║
║      LC = 15 × average annual operational losses (10-year window)        ║
║      Bucket 1 default: ILM = 1.0 (national discretion §RBC30.41)         ║
║      Insufficient loss data (<5y): ILM = 1.0                             ║
║                                                                          ║
║  ORC      = BIC × ILM                                                    ║
║  RWA_op   = ORC × 12.5                                                   ║
║                                                                          ║
║  Per Rule 1: every SMAResult surfaces                                    ║
║    bi_three_year_avg_kes + bic_kes + lc_kes + ilm + orc_kes              ║
║    + rwa_op_kes + bucket + ilm_source + framework_refs                   ║
║                                                                          ║
║  Per Rule 7: engine is computational only — never auto-records loss     ║
║  events, never approves capital. All inputs caller-provided. ILM         ║
║  national-discretion override is a caller flag, not engine policy.       ║
║                                                                          ║
║  Pure stdlib (math + Decimal). No scipy.                                 ║
║                                                                          ║
║  Composes with:                                                          ║
║    - finance (BI inputs sourced from P&L statements)                     ║
║    - audit_grc (operational loss taxonomy — future composition)          ║
║    - market_risk_limits (op-risk RWA limits — future composition)        ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Tuple

SPEC_DEVIATION_NOTE = (
    "OperationalRiskSMA implements ENH-OR-001 BCBS d457 §RBC30 "
    "Standardized Measurement Approach. Pure stdlib via math + "
    "Decimal. Per Rule 1, every SMAResult surfaces all inputs + "
    "computed intermediates (BI 3y avg, LC, BIC, ILM) + outputs "
    "(ORC, RWA_op). Per Rule 7, engine is computational only — "
    "never records losses, never approves capital allocations. "
    "Bucket thresholds are EUR per BCBS d457; KES conversion is a "
    "caller-supplied parameter. ILM = 1.0 fallback when bucket 1 "
    "or insufficient loss history (<5 years) per §RBC30.41."
)

# ════════════════════════════════════════════════════════════════════════
# Constants per BCBS d457 §RBC30
# ════════════════════════════════════════════════════════════════════════

# Marginal alpha coefficients per bucket
ALPHA_BUCKET_1 = Decimal("0.12")   # BI ≤ 1bn EUR
ALPHA_BUCKET_2 = Decimal("0.15")   # 1bn < BI ≤ 30bn EUR
ALPHA_BUCKET_3 = Decimal("0.18")   # BI > 30bn EUR

# Bucket thresholds in EUR
BUCKET_1_CEILING_EUR = Decimal("1000000000")     # 1bn
BUCKET_2_CEILING_EUR = Decimal("30000000000")    # 30bn

# ILDC ceiling: |NII| capped at 2.25% of interest-earning assets
ILDC_NII_CAP_RATIO = Decimal("0.0225")

# LC multiplier per BCBS d457 §RBC30.21
LC_MULTIPLIER = Decimal("15")

# ILM constants — formula: ln(e − 1 + (LC/BIC)^0.8)
ILM_EXPONENT = Decimal("0.8")

# Minimum loss-history depth before ILM is computed (years)
MIN_LOSS_HISTORY_YEARS = 5
LOSS_HISTORY_WINDOW_YEARS = 10

# RWA multiplier (Basel 8% capital ratio inverse)
RWA_MULTIPLIER = Decimal("12.5")

# Years of BI averaged (BCBS d457 §RBC30.6)
BI_AVERAGE_YEARS = 3


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class Bucket(Enum):
    """BCBS d457 §RBC30.5 bucket assignment."""
    BUCKET_1 = "BUCKET_1"   # BI ≤ 1bn EUR
    BUCKET_2 = "BUCKET_2"   # 1bn < BI ≤ 30bn EUR
    BUCKET_3 = "BUCKET_3"   # BI > 30bn EUR


class ILMSource(Enum):
    """How the ILM value was determined per Rule 1."""
    COMPUTED = "COMPUTED"                          # Full formula applied
    BUCKET_1_DISCRETION = "BUCKET_1_DISCRETION"    # ILM=1, §RBC30.41 opt-out
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"  # <5y losses → ILM=1


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BusinessIndicatorInputs:
    """Inputs for one financial year used to compute BI.

    All values in KES, signed (P&L items can be negative).
    """
    fiscal_year: int
    # ILDC inputs
    interest_income_kes: Decimal
    interest_expense_kes: Decimal
    interest_earning_assets_kes: Decimal
    dividend_income_kes: Decimal
    # SC inputs
    other_operating_income_kes: Decimal
    other_operating_expense_kes: Decimal
    fee_income_kes: Decimal
    fee_expense_kes: Decimal
    # FC inputs (already net of opposite-sign offsets per §RBC30.13)
    net_pnl_trading_book_kes: Decimal
    net_pnl_banking_book_kes: Decimal

    def __post_init__(self) -> None:
        if self.interest_earning_assets_kes < 0:
            raise ValueError(
                f"FY{self.fiscal_year}: IEA cannot be negative")
        # Most P&L items can be negative — no further sign checks


@dataclass(frozen=True)
class OperationalLossEvent:
    """A single operational loss event aggregated to annual buckets
    by the caller before being passed in.

    Per BCBS d457 §RBC30.20, only losses ≥ EUR 20k threshold are
    included. The caller applies the threshold; the engine sums
    what it receives.
    """
    fiscal_year: int
    gross_loss_kes: Decimal

    def __post_init__(self) -> None:
        if self.gross_loss_kes < 0:
            raise ValueError(
                f"FY{self.fiscal_year}: gross_loss_kes must be ≥ 0")


@dataclass(frozen=True)
class SMAInputs:
    """Aggregate inputs for one SMA computation.

    Per Rule 7, all data is caller-provided. The engine never
    fetches or modifies loss data.
    """
    bi_inputs: Tuple[BusinessIndicatorInputs, ...]    # last 3 years
    loss_events: Tuple[OperationalLossEvent, ...]     # last 10 years
    eur_to_kes_rate: Decimal                          # current spot
    apply_bucket_1_discretion: bool = True            # §RBC30.41

    def __post_init__(self) -> None:
        if len(self.bi_inputs) != BI_AVERAGE_YEARS:
            raise ValueError(
                f"SMA requires exactly {BI_AVERAGE_YEARS} years of BI "
                f"inputs (got {len(self.bi_inputs)})")
        if self.eur_to_kes_rate <= 0:
            raise ValueError("eur_to_kes_rate must be positive")
        years = {bi.fiscal_year for bi in self.bi_inputs}
        if len(years) != BI_AVERAGE_YEARS:
            raise ValueError("BI inputs must cover distinct years")


@dataclass(frozen=True)
class SMAResult:
    """Output of the SMA computation.

    Per Rule 1, surfaces all intermediates: BI per year, BI 3y
    average, LC, BIC, ILM, ORC, RWA, bucket assignment, ILM source.
    """
    bi_per_year_kes: Tuple[Tuple[int, Decimal], ...]
    bi_three_year_avg_kes: Decimal
    bi_three_year_avg_eur: Decimal
    bucket: Bucket
    bic_kes: Decimal
    annual_avg_loss_kes: Decimal
    lc_kes: Decimal
    ilm: Decimal
    ilm_source: ILMSource
    orc_kes: Decimal
    rwa_op_kes: Decimal
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class OperationalRiskSMA:
    """BCBS d457 SMA capital engine.

    Per Rule 7, computational only. The engine never:
      - records loss events
      - approves capital allocations
      - overrides national-discretion flags (caller-supplied)
    """

    # ── Component computations ────────────────────────────────────────
    @staticmethod
    def _ildc(bi: BusinessIndicatorInputs) -> Decimal:
        """ILDC = min(|II − IE|, 0.0225 × IEA) + DI."""
        nii_abs = abs(bi.interest_income_kes - bi.interest_expense_kes)
        cap = ILDC_NII_CAP_RATIO * bi.interest_earning_assets_kes
        return min(nii_abs, cap) + bi.dividend_income_kes

    @staticmethod
    def _sc(bi: BusinessIndicatorInputs) -> Decimal:
        """SC = max(OI, OE) + max(FI, FE)."""
        return (
            max(bi.other_operating_income_kes,
                bi.other_operating_expense_kes)
            + max(bi.fee_income_kes, bi.fee_expense_kes))

    @staticmethod
    def _fc(bi: BusinessIndicatorInputs) -> Decimal:
        """FC = |Net P&L TB| + |Net P&L BB|."""
        return (abs(bi.net_pnl_trading_book_kes)
                + abs(bi.net_pnl_banking_book_kes))

    def _bi_for_year(self, bi: BusinessIndicatorInputs) -> Decimal:
        """BI for one year = ILDC + SC + FC."""
        return self._ildc(bi) + self._sc(bi) + self._fc(bi)

    # ── Bucket assignment + BIC ───────────────────────────────────────
    def _bucket(self, bi_avg_eur: Decimal) -> Bucket:
        if bi_avg_eur <= BUCKET_1_CEILING_EUR:
            return Bucket.BUCKET_1
        if bi_avg_eur <= BUCKET_2_CEILING_EUR:
            return Bucket.BUCKET_2
        return Bucket.BUCKET_3

    def _bic_kes(
        self, bi_avg_kes: Decimal, bi_avg_eur: Decimal,
        eur_to_kes: Decimal,
    ) -> Decimal:
        """Marginal-coefficient BIC per BCBS d457 §RBC30.5.

        Coefficients apply marginally to portions of BI within
        each bucket. Computed in EUR then converted to KES so
        bucket cutoffs are exact per BCBS thresholds.
        """
        bic_eur = Decimal("0")
        if bi_avg_eur <= BUCKET_1_CEILING_EUR:
            bic_eur = ALPHA_BUCKET_1 * bi_avg_eur
        elif bi_avg_eur <= BUCKET_2_CEILING_EUR:
            bic_eur = (
                ALPHA_BUCKET_1 * BUCKET_1_CEILING_EUR
                + ALPHA_BUCKET_2 * (bi_avg_eur - BUCKET_1_CEILING_EUR))
        else:
            bic_eur = (
                ALPHA_BUCKET_1 * BUCKET_1_CEILING_EUR
                + ALPHA_BUCKET_2 * (BUCKET_2_CEILING_EUR
                                     - BUCKET_1_CEILING_EUR)
                + ALPHA_BUCKET_3 * (bi_avg_eur - BUCKET_2_CEILING_EUR))
        return bic_eur * eur_to_kes

    # ── Loss component + ILM ──────────────────────────────────────────
    def _annual_average_loss(
        self, losses: Tuple[OperationalLossEvent, ...],
    ) -> Tuple[Decimal, int]:
        """Returns (avg, distinct_years)."""
        if not losses:
            return (Decimal("0"), 0)
        by_year: dict[int, Decimal] = {}
        for ev in losses:
            by_year[ev.fiscal_year] = (
                by_year.get(ev.fiscal_year, Decimal("0"))
                + ev.gross_loss_kes)
        years_count = len(by_year)
        # Average over the actual window length (capped at 10y)
        denom = min(years_count, LOSS_HISTORY_WINDOW_YEARS)
        if denom == 0:
            return (Decimal("0"), 0)
        total = sum(by_year.values(), Decimal("0"))
        return (total / Decimal(denom), years_count)

    def _ilm(
        self, lc: Decimal, bic: Decimal,
        bucket: Bucket, years_count: int,
        apply_bucket_1_discretion: bool,
    ) -> Tuple[Decimal, ILMSource]:
        """ILM = ln(e − 1 + (LC/BIC)^0.8), or 1.0 by national
        discretion / insufficient history.

        Returns (ilm_value, source) per Rule 1.
        """
        if (bucket == Bucket.BUCKET_1
                and apply_bucket_1_discretion):
            return (Decimal("1"), ILMSource.BUCKET_1_DISCRETION)
        if years_count < MIN_LOSS_HISTORY_YEARS:
            return (Decimal("1"), ILMSource.INSUFFICIENT_HISTORY)
        if bic <= 0:
            # Defensive: BIC = 0 means no BI — ILM undefined; surface 1
            return (Decimal("1"), ILMSource.INSUFFICIENT_HISTORY)
        # Compute via float (math.log/math.exp), Decimal-quantized at end
        ratio = float(lc / bic)
        e = math.e
        ilm_f = math.log(e - 1.0 + ratio ** float(ILM_EXPONENT))
        # ILM should not be negative — clamp at 0 (very low LC)
        if ilm_f < 0:
            ilm_f = 0.0
        return (Decimal(str(ilm_f)), ILMSource.COMPUTED)

    # ── Public API ────────────────────────────────────────────────────
    def compute(self, inputs: SMAInputs) -> SMAResult:
        """Run the full SMA pipeline."""
        # 1. BI per year + 3y average
        bi_per_year = tuple(
            (bi.fiscal_year, self._bi_for_year(bi))
            for bi in inputs.bi_inputs)
        bi_total = sum(
            (val for _, val in bi_per_year), Decimal("0"))
        bi_avg_kes = bi_total / Decimal(BI_AVERAGE_YEARS)
        bi_avg_eur = bi_avg_kes / inputs.eur_to_kes_rate

        # 2. Bucket + BIC
        bucket = self._bucket(bi_avg_eur)
        bic_kes = self._bic_kes(
            bi_avg_kes, bi_avg_eur, inputs.eur_to_kes_rate)

        # 3. LC + ILM
        annual_avg_loss, years_count = self._annual_average_loss(
            inputs.loss_events)
        lc_kes = LC_MULTIPLIER * annual_avg_loss
        ilm, ilm_source = self._ilm(
            lc=lc_kes, bic=bic_kes, bucket=bucket,
            years_count=years_count,
            apply_bucket_1_discretion=(
                inputs.apply_bucket_1_discretion))

        # 4. ORC + RWA
        orc_kes = bic_kes * ilm
        rwa_op_kes = orc_kes * RWA_MULTIPLIER

        return SMAResult(
            bi_per_year_kes=tuple(
                (yr, val.quantize(Decimal("0.01")))
                for yr, val in bi_per_year),
            bi_three_year_avg_kes=bi_avg_kes.quantize(
                Decimal("0.01")),
            bi_three_year_avg_eur=bi_avg_eur.quantize(
                Decimal("0.01")),
            bucket=bucket,
            bic_kes=bic_kes.quantize(Decimal("0.01")),
            annual_avg_loss_kes=annual_avg_loss.quantize(
                Decimal("0.01")),
            lc_kes=lc_kes.quantize(Decimal("0.01")),
            ilm=ilm.quantize(Decimal("0.000001")),
            ilm_source=ilm_source,
            orc_kes=orc_kes.quantize(Decimal("0.01")),
            rwa_op_kes=rwa_op_kes.quantize(Decimal("0.01")),
            framework_refs=(
                "BCBS d457 §RBC30 Standardised Approach",
                "Basel III Operational Risk Framework",
                "CBK PG/15 Risk Management Guidelines"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _bi(year: int, **overrides) -> BusinessIndicatorInputs:
    """Helper: build a BI input with reasonable defaults."""
    base = dict(
        fiscal_year=year,
        interest_income_kes=Decimal("12000000000"),    # 12bn KES
        interest_expense_kes=Decimal("6000000000"),    # 6bn
        interest_earning_assets_kes=Decimal("400000000000"),
        dividend_income_kes=Decimal("100000000"),
        other_operating_income_kes=Decimal("500000000"),
        other_operating_expense_kes=Decimal("400000000"),
        fee_income_kes=Decimal("3000000000"),
        fee_expense_kes=Decimal("500000000"),
        net_pnl_trading_book_kes=Decimal("200000000"),
        net_pnl_banking_book_kes=Decimal("100000000"))
    base.update(overrides)
    return BusinessIndicatorInputs(**base)


def _test_bi_inputs_validate_iea_non_negative():
    try:
        _bi(2023, interest_earning_assets_kes=Decimal("-1"))
        assert False
    except ValueError:
        pass


def _test_loss_event_validates_non_negative():
    try:
        OperationalLossEvent(
            fiscal_year=2023,
            gross_loss_kes=Decimal("-1"))
        assert False
    except ValueError:
        pass


def _test_sma_inputs_require_three_years():
    try:
        SMAInputs(
            bi_inputs=(_bi(2023),),
            loss_events=(),
            eur_to_kes_rate=Decimal("145"))
        assert False
    except ValueError:
        pass


def _test_sma_inputs_reject_duplicate_years():
    try:
        SMAInputs(
            bi_inputs=(_bi(2023), _bi(2023), _bi(2024)),
            loss_events=(),
            eur_to_kes_rate=Decimal("145"))
        assert False
    except ValueError:
        pass


def _test_sma_inputs_reject_zero_eur_rate():
    try:
        SMAInputs(
            bi_inputs=(_bi(2021), _bi(2022), _bi(2023)),
            loss_events=(),
            eur_to_kes_rate=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_ildc_uses_nii_cap_when_unsecured_high():
    """ILDC NII portion capped at 2.25% × IEA."""
    eng = OperationalRiskSMA()
    bi = _bi(2023,
             interest_income_kes=Decimal("100000000000"),
             interest_expense_kes=Decimal("0"),
             interest_earning_assets_kes=Decimal("400000000000"),
             dividend_income_kes=Decimal("0"))
    # |NII| = 100bn, cap = 0.0225 × 400bn = 9bn → ILDC = 9bn
    assert eng._ildc(bi) == Decimal("9000000000")


def _test_sc_uses_max_of_each_pair():
    """SC = max(OI, OE) + max(FI, FE)."""
    eng = OperationalRiskSMA()
    bi = _bi(2023,
             other_operating_income_kes=Decimal("100"),
             other_operating_expense_kes=Decimal("300"),
             fee_income_kes=Decimal("500"),
             fee_expense_kes=Decimal("200"))
    # max(100, 300) + max(500, 200) = 300 + 500 = 800
    assert eng._sc(bi) == Decimal("800")


def _test_fc_uses_absolute_values():
    """FC = |TB| + |BB|, sign-insensitive."""
    eng = OperationalRiskSMA()
    bi = _bi(2023,
             net_pnl_trading_book_kes=Decimal("-500"),
             net_pnl_banking_book_kes=Decimal("300"))
    assert eng._fc(bi) == Decimal("800")


def _test_bucket_assignment_at_thresholds():
    eng = OperationalRiskSMA()
    assert eng._bucket(Decimal("999999999")) == Bucket.BUCKET_1
    assert eng._bucket(Decimal("1000000000")) == Bucket.BUCKET_1
    assert eng._bucket(Decimal("1000000001")) == Bucket.BUCKET_2
    assert eng._bucket(Decimal("30000000000")) == Bucket.BUCKET_2
    assert eng._bucket(Decimal("30000000001")) == Bucket.BUCKET_3


def _test_bic_marginal_application_bucket_2():
    """BI = 5bn EUR → BIC = 0.12×1bn + 0.15×4bn = 720m EUR."""
    eng = OperationalRiskSMA()
    rate = Decimal("145")
    bi_eur = Decimal("5000000000")
    bi_kes = bi_eur * rate
    bic_kes = eng._bic_kes(bi_kes, bi_eur, rate)
    expected_eur = (
        ALPHA_BUCKET_1 * BUCKET_1_CEILING_EUR
        + ALPHA_BUCKET_2 * (bi_eur - BUCKET_1_CEILING_EUR))
    assert bic_kes == expected_eur * rate


def _test_bucket_1_discretion_forces_ilm_one():
    """Small bank in bucket 1 with discretion → ILM = 1."""
    eng = OperationalRiskSMA()
    inputs = SMAInputs(
        bi_inputs=(_bi(2021), _bi(2022), _bi(2023)),
        loss_events=tuple(
            OperationalLossEvent(
                fiscal_year=y,
                gross_loss_kes=Decimal("100000000"))
            for y in range(2014, 2024)),
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=True)
    r = eng.compute(inputs)
    assert r.bucket == Bucket.BUCKET_1
    assert r.ilm == Decimal("1.000000")
    assert r.ilm_source == ILMSource.BUCKET_1_DISCRETION
    # ORC = BIC × 1
    assert r.orc_kes == r.bic_kes


def _test_insufficient_loss_history_forces_ilm_one():
    """Bucket 2 without sufficient loss history → ILM = 1."""
    eng = OperationalRiskSMA()
    big = dict(
        interest_income_kes=Decimal("700000000000"),
        interest_expense_kes=Decimal("300000000000"),
        interest_earning_assets_kes=Decimal("20000000000000"),
        fee_income_kes=Decimal("80000000000"))
    inputs = SMAInputs(
        bi_inputs=(_bi(2021, **big), _bi(2022, **big),
                   _bi(2023, **big)),
        loss_events=tuple(
            OperationalLossEvent(
                fiscal_year=y,
                gross_loss_kes=Decimal("1000000000"))
            for y in (2022, 2023)),  # only 2 years
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=False)
    r = eng.compute(inputs)
    assert r.bucket in (Bucket.BUCKET_2, Bucket.BUCKET_3), \
        f"setup wrong: bucket={r.bucket}"
    assert r.ilm_source == ILMSource.INSUFFICIENT_HISTORY
    assert r.ilm == Decimal("1.000000")


def _test_ilm_computed_when_bucket_2_sufficient_history():
    """Bucket 2 with 10y of losses → ILM computed via formula."""
    eng = OperationalRiskSMA()
    big = dict(
        interest_income_kes=Decimal("700000000000"),
        interest_expense_kes=Decimal("300000000000"),
        interest_earning_assets_kes=Decimal("20000000000000"),
        fee_income_kes=Decimal("80000000000"))
    inputs = SMAInputs(
        bi_inputs=(_bi(2021, **big), _bi(2022, **big),
                   _bi(2023, **big)),
        loss_events=tuple(
            OperationalLossEvent(
                fiscal_year=y,
                gross_loss_kes=Decimal("5000000000"))
            for y in range(2014, 2024)),
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=False)
    r = eng.compute(inputs)
    assert r.ilm_source == ILMSource.COMPUTED
    assert r.ilm > Decimal("0")
    # ORC = BIC × ILM (using full-precision ILM; r.ilm is quantized
    # to 6dp, so we tolerate small rounding within KES 100k on
    # multi-billion BIC for the recomputation cross-check).
    expected_orc = (r.bic_kes * r.ilm).quantize(Decimal("0.01"))
    diff = abs(r.orc_kes - expected_orc)
    assert diff < Decimal("100000"), (
        f"ORC {r.orc_kes} too far from BIC×ILM {expected_orc} "
        f"(diff {diff})")


def _test_ilm_monotonic_in_loss_size():
    """Holding BIC constant, larger losses → larger ILM."""
    eng = OperationalRiskSMA()
    big = dict(
        interest_income_kes=Decimal("700000000000"),
        interest_expense_kes=Decimal("300000000000"),
        interest_earning_assets_kes=Decimal("20000000000000"),
        fee_income_kes=Decimal("80000000000"))

    def run(loss_per_year_kes: Decimal) -> Decimal:
        inp = SMAInputs(
            bi_inputs=(_bi(2021, **big), _bi(2022, **big),
                       _bi(2023, **big)),
            loss_events=tuple(
                OperationalLossEvent(
                    fiscal_year=y, gross_loss_kes=loss_per_year_kes)
                for y in range(2014, 2024)),
            eur_to_kes_rate=Decimal("145"),
            apply_bucket_1_discretion=False)
        return eng.compute(inp).ilm

    low = run(Decimal("1000000000"))
    high = run(Decimal("10000000000"))
    assert high > low, f"ILM not monotonic: low={low}, high={high}"


def _test_rwa_equals_orc_times_125():
    """RWA_op = ORC × 12.5 identity."""
    eng = OperationalRiskSMA()
    inputs = SMAInputs(
        bi_inputs=(_bi(2021), _bi(2022), _bi(2023)),
        loss_events=(),
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=True)
    r = eng.compute(inputs)
    expected = (r.orc_kes * Decimal("12.5")).quantize(Decimal("0.01"))
    assert r.rwa_op_kes == expected


def _test_result_surfaces_full_provenance():
    """Per Rule 1: all inputs + intermediates + outputs surfaced."""
    eng = OperationalRiskSMA()
    inputs = SMAInputs(
        bi_inputs=(_bi(2021), _bi(2022), _bi(2023)),
        loss_events=(),
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=True)
    r = eng.compute(inputs)
    assert len(r.bi_per_year_kes) == 3
    assert r.bi_three_year_avg_kes > 0
    assert r.bi_three_year_avg_eur > 0
    assert r.bucket in tuple(Bucket)
    assert r.bic_kes > 0
    assert r.ilm_source in tuple(ILMSource)
    assert len(r.framework_refs) >= 2
    assert any("BCBS d457" in ref for ref in r.framework_refs)


def _test_loss_aggregation_groups_by_year():
    """Multiple events same year sum into one annual figure."""
    eng = OperationalRiskSMA()
    events = (
        OperationalLossEvent(2023, Decimal("100")),
        OperationalLossEvent(2023, Decimal("200")),
        OperationalLossEvent(2022, Decimal("400")),
    )
    avg, years = eng._annual_average_loss(events)
    # 2023: 300, 2022: 400 → total 700, 2 years → avg 350
    assert avg == Decimal("350")
    assert years == 2


def self_test() -> None:
    tests = [
        _test_bi_inputs_validate_iea_non_negative,
        _test_loss_event_validates_non_negative,
        _test_sma_inputs_require_three_years,
        _test_sma_inputs_reject_duplicate_years,
        _test_sma_inputs_reject_zero_eur_rate,
        _test_ildc_uses_nii_cap_when_unsecured_high,
        _test_sc_uses_max_of_each_pair,
        _test_fc_uses_absolute_values,
        _test_bucket_assignment_at_thresholds,
        _test_bic_marginal_application_bucket_2,
        _test_bucket_1_discretion_forces_ilm_one,
        _test_insufficient_loss_history_forces_ilm_one,
        _test_ilm_computed_when_bucket_2_sufficient_history,
        _test_ilm_monotonic_in_loss_size,
        _test_rwa_equals_orc_times_125,
        _test_result_surfaces_full_provenance,
        _test_loss_aggregation_groups_by_year,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ op_risk self-test: {len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ op_risk self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

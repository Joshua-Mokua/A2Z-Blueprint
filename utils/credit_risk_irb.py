"""utils/credit_risk_irb.py — v10.42: Credit Risk IRB Capital Framework.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-CR-001 — IRB Capital (PD / LGD / EAD / RWA)                       ║
║  Cat A — Risk arc continuation                                         ║
╠════════════════════════════════════════════════════════════════════════╣
║  Distinct from utils.credit_risk_scoring (underwriting) and            ║
║  utils.ifrs9_classification (accounting). This module covers the       ║
║  REGULATORY CAPITAL perspective per BCBS d424 IRB framework.           ║
║                                                                         ║
║  Inputs:                                                                ║
║    - PD (probability of default, 1-year horizon)                       ║
║    - LGD (loss given default, %)                                       ║
║    - EAD (exposure at default, KES)                                    ║
║    - M (effective maturity, years)                                     ║
║                                                                         ║
║  Outputs:                                                               ║
║    - K (regulatory capital requirement, %)                             ║
║    - RWA (risk-weighted assets, KES)                                   ║
║    - Expected Loss (PD × LGD × EAD)                                    ║
║                                                                         ║
║  Per BCBS d424 §RBC25 corporate exposure formula:                       ║
║    K = LGD × [N((1-R)^-0.5 × N^-1(PD)                                  ║
║              + (R/(1-R))^0.5 × N^-1(0.999)) - PD]                      ║
║          × (1 + (M-2.5) × b(PD)) / (1 - 1.5 × b(PD))                   ║
║                                                                         ║
║    R = 0.12 × (1 - exp(-50×PD)) / (1 - exp(-50))                       ║
║          + 0.24 × [1 - (1 - exp(-50×PD))/(1 - exp(-50))]               ║
║                                                                         ║
║    b(PD) = (0.11852 - 0.05478 × ln(PD))^2                              ║
║                                                                         ║
║    RWA = K × 12.5 × EAD                                                ║
║                                                                         ║
║  Per Rule 1: every CapitalResult surfaces                              ║
║    pd + lgd + ead + maturity + correlation_R + maturity_adj_b          ║
║    + capital_requirement_pct + rwa_kes + expected_loss_kes             ║
║    + framework_refs                                                     ║
║                                                                         ║
║  Per Rule 7: engine is computational only — never moves loans          ║
║  between exposure classes, never auto-approves capital allocations.    ║
║  All approvals flow through ALCO + Capital Management Committee.       ║
║                                                                         ║
║  Pure stdlib (statistics.NormalDist + math). No scipy.                 ║
║                                                                         ║
║  Composes with:                                                         ║
║    - credit_risk_scoring (underwriting PD becomes IRB PD input)        ║
║    - climate_pd_overlay (PD-adjusted via v10.6-10 overlay)             ║
║    - ifrs9_classification (Stage 2/3 informs LGD)                      ║
║    - market_risk_limits (capital RWA limits — future composition)      ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SPEC_DEVIATION_NOTE = (
    "CreditRiskIRB implements ENH-CR-001 BCBS d424 IRB corporate "
    "exposure formula. Pure stdlib via statistics.NormalDist + math. "
    "Per Rule 1, every CapitalResult surfaces all inputs + computed "
    "intermediate values (correlation R, maturity adjustment b) + "
    "outputs. Per Rule 7, computational only — never moves loans "
    "between exposure classes, never auto-approves capital. Decimal "
    "for monetary; float for probability inputs (NormalDist requires "
    "float). Confidence level 99.9% per BCBS d424 §RBC25.4."
)

# ════════════════════════════════════════════════════════════════════════
# Constants per BCBS d424
# ════════════════════════════════════════════════════════════════════════

CONFIDENCE_999 = 0.999            # Basel ASRF confidence per §RBC25.4
RWA_MULTIPLIER = Decimal("12.5")  # 1/0.08 — Basel 8% capital ratio
PD_FLOOR = 0.0003                 # Per BCBS d424 §RBC25.6 (3 bps)
PD_DEFAULT_CEILING = 1.0          # PD = 1 means defaulted
LGD_FLOOR = 0.0                   # No minimum (varies by exposure class)
LGD_CEILING = 1.0                 # 100%
M_FLOOR = 1.0                     # Per BCBS d424 §RBC25.13
M_CEILING = 5.0                   # Per BCBS d424 §RBC25.13


class ExposureClass(Enum):
    """BCBS d424 §RBC25 exposure classes.

    Corporate scope (v10.42):
      - LARGE_CORPORATE, SME_CORPORATE

    Retail scope (v10.313 — B-008 close):
      - RETAIL_RESIDENTIAL_MORTGAGE (§RBC25.21, R=0.15 const)
      - QUALIFYING_REVOLVING_RETAIL (§RBC25.23, R=0.04 const)
      - OTHER_RETAIL (§RBC25.22, R = 0.03 + 0.13*W where
                       W uses 35×PD, not 50×PD)

    Per §RBC25.20, retail exposures have NO maturity
    adjustment (mat_factor = 1.0 regardless of M).

    Not yet implemented:
      - SOVEREIGN
      - BANK
    """
    LARGE_CORPORATE = "LARGE_CORPORATE"     # >EUR 500m turnover
    SME_CORPORATE = "SME_CORPORATE"         # SME treated as corporate
    SOVEREIGN = "SOVEREIGN"                 # not implemented in v10.42
    BANK = "BANK"                           # not implemented in v10.42
    # v10.313 — retail scope, B-008 close
    RETAIL_RESIDENTIAL_MORTGAGE = "RETAIL_RESIDENTIAL_MORTGAGE"
    QUALIFYING_REVOLVING_RETAIL = "QUALIFYING_REVOLVING_RETAIL"
    OTHER_RETAIL = "OTHER_RETAIL"


# Sets used by the engine to dispatch correlation/maturity logic
_RETAIL_CLASSES = frozenset({
    ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE,
    ExposureClass.QUALIFYING_REVOLVING_RETAIL,
    ExposureClass.OTHER_RETAIL,
})

_CORPORATE_CLASSES = frozenset({
    ExposureClass.LARGE_CORPORATE,
    ExposureClass.SME_CORPORATE,
})

_IMPLEMENTED_CLASSES = _CORPORATE_CLASSES | _RETAIL_CLASSES


def product_to_exposure_class(product: str) -> "ExposureClass":
    """Map an IFRS9 product string to its IRB ExposureClass.

    Used by credit_portfolio_analytics to dispatch each loan
    in data/ifrs9_loans.json to the right Basel class rather
    than mapping everything to SME_CORPORATE (the v10.309
    shape-fit caveat that this batch removes).

    Mapping rules (in priority order):
      1. Mortgage / Home Loan / Housing → RETAIL_RESIDENTIAL_MORTGAGE
      2. Credit Card / Overdraft / Revolving → QUALIFYING_REVOLVING_RETAIL
      3. Motor Vehicle / Personal / Salary / Consumer
         → OTHER_RETAIL
      4. SME / Trade Finance / Working Capital / Asset Finance
         → SME_CORPORATE
      5. Anything containing "Corporate" or "Large"
         → LARGE_CORPORATE
      6. Anything else → SME_CORPORATE (safe default —
         matches pre-v10.313 behavior for unknown inputs)

    All matching is case-insensitive and substring-based.
    """
    if not isinstance(product, str) or not product.strip():
        return ExposureClass.SME_CORPORATE

    p = product.lower()

    # 1. Residential mortgage
    if any(kw in p for kw in (
        "mortgage", "home loan", "housing",
    )):
        return ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE

    # 2. Qualifying revolving retail
    if any(kw in p for kw in (
        "credit card", "overdraft", "revolving",
    )):
        return ExposureClass.QUALIFYING_REVOLVING_RETAIL

    # 3. Other retail
    if any(kw in p for kw in (
        "motor vehicle", "personal", "salary",
        "consumer",
    )):
        return ExposureClass.OTHER_RETAIL

    # 5. Large corporate (check before SME so "Large
    #    Corporate" wins over generic catch)
    if "large corporate" in p or "large-corp" in p:
        return ExposureClass.LARGE_CORPORATE

    # 4. SME / corporate finance products
    if any(kw in p for kw in (
        "sme", "trade finance", "working capital",
        "asset finance", "corporate",
    )):
        return ExposureClass.SME_CORPORATE

    # 6. Safe default — same as pre-v10.313 behavior for
    #    unknown inputs
    return ExposureClass.SME_CORPORATE


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class IRBExposure:
    """Single IRB-eligible exposure with all required inputs."""
    exposure_id: str
    exposure_class: ExposureClass
    pd: float                      # 1-year, in [PD_FLOOR, 1.0]
    lgd: float                     # in [0, 1]
    ead_kes: Decimal               # positive
    maturity_years: float          # in [1, 5]
    notes: str = ""

    def __post_init__(self) -> None:
        if not (PD_FLOOR <= self.pd <= PD_DEFAULT_CEILING):
            raise ValueError(
                f"exposure {self.exposure_id}: PD={self.pd} outside "
                f"[{PD_FLOOR}, {PD_DEFAULT_CEILING}]")
        if not (LGD_FLOOR <= self.lgd <= LGD_CEILING):
            raise ValueError(
                f"exposure {self.exposure_id}: LGD={self.lgd} outside "
                f"[{LGD_FLOOR}, {LGD_CEILING}]")
        if self.ead_kes <= 0:
            raise ValueError(
                f"exposure {self.exposure_id}: EAD must be positive "
                f"(got {self.ead_kes})")
        if not (M_FLOOR <= self.maturity_years <= M_CEILING):
            raise ValueError(
                f"exposure {self.exposure_id}: M={self.maturity_years} "
                f"outside [{M_FLOOR}, {M_CEILING}]")
        if self.exposure_class not in _IMPLEMENTED_CLASSES:
            raise ValueError(
                f"exposure {self.exposure_id}: class "
                f"{self.exposure_class.value} not yet implemented "
                f"(v10.313 supports LARGE_CORPORATE, "
                f"SME_CORPORATE, RETAIL_RESIDENTIAL_MORTGAGE, "
                f"QUALIFYING_REVOLVING_RETAIL, OTHER_RETAIL)")


@dataclass(frozen=True)
class CapitalResult:
    """Output of the IRB capital computation.

    Per Rule 1, surfaces all inputs + intermediate values + outputs.
    """
    exposure_id: str
    exposure_class: ExposureClass
    pd: float
    lgd: float
    ead_kes: Decimal
    maturity_years: float
    correlation_R: float                # intermediate
    maturity_adj_b: float               # intermediate
    capital_requirement_pct: Decimal    # K, %
    rwa_kes: Decimal                    # K × 12.5 × EAD
    expected_loss_kes: Decimal          # PD × LGD × EAD
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class IRBCapitalEngine:
    """Computes BCBS d424 IRB capital requirements for corporate
    exposures.

    Per Rule 7, the engine is purely computational. It never
    classifies loans, never executes capital allocations, never
    overrides PD/LGD/EAD inputs. All inputs are caller-provided.
    """

    def __init__(self) -> None:
        self._normal = statistics.NormalDist()

    # ── Internal helpers ──────────────────────────────────────────────
    def _correlation(self, pd: float) -> float:
        """R = 0.12 × W + 0.24 × (1 - W)
        where W = (1 - exp(-50×PD)) / (1 - exp(-50))
        Per BCBS d424 §RBC25.7 corporate exposure correlation."""
        # Guard against PD = 0 (would fail PD_FLOOR but be defensive)
        if pd <= 0:
            pd = PD_FLOOR
        denom = 1.0 - math.exp(-50.0)
        w = (1.0 - math.exp(-50.0 * pd)) / denom
        return 0.12 * w + 0.24 * (1.0 - w)

    def _correlation_retail(
        self, pd: float, exposure_class: "ExposureClass",
    ) -> float:
        """Retail asset correlation per BCBS d424 §RBC25.21-23.

        Three retail formulas (one per retail class):

        RETAIL_RESIDENTIAL_MORTGAGE (§RBC25.21):
            R = 0.15 (constant, independent of PD)

        QUALIFYING_REVOLVING_RETAIL (§RBC25.23):
            R = 0.04 (constant)

        OTHER_RETAIL (§RBC25.22):
            R = 0.03 × (1 - exp(-35×PD)) / (1 - exp(-35))
              + 0.16 × (1 - (1 - exp(-35×PD)) / (1 - exp(-35)))

            Equivalently (factored form used here):
            R = 0.03 + 0.13 × W
            where W = (1 - exp(-35×PD)) / (1 - exp(-35))

            Note the difference from corporate: -35×PD
            (not -50×PD) and bounds [0.03, 0.16] (not
            [0.12, 0.24]).

        Defensive: guards against PD ≤ 0 (would fail PD_FLOOR
        but doesn't crash).
        """
        if pd <= 0:
            pd = PD_FLOOR
        if exposure_class == ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE:
            return 0.15
        if exposure_class == ExposureClass.QUALIFYING_REVOLVING_RETAIL:
            return 0.04
        if exposure_class == ExposureClass.OTHER_RETAIL:
            denom = 1.0 - math.exp(-35.0)
            w = (1.0 - math.exp(-35.0 * pd)) / denom
            return 0.03 + 0.13 * w
        raise ValueError(
            f"_correlation_retail called with non-retail "
            f"class {exposure_class}"
        )

    def _maturity_adjustment(self, pd: float) -> float:
        """b(PD) = (0.11852 - 0.05478 × ln(PD))^2
        Per BCBS d424 §RBC25.13."""
        if pd <= 0:
            pd = PD_FLOOR
        return (0.11852 - 0.05478 * math.log(pd)) ** 2

    def _capital_requirement_pct(
        self, pd: float, lgd: float, m: float,
        exposure_class: "ExposureClass" = (
            ExposureClass.LARGE_CORPORATE),
    ) -> Tuple[Decimal, float, float]:
        """K per BCBS d424 §RBC25.5 (corporate) or §RBC25.20+
        (retail).

        Dispatches on exposure_class:
          - Corporate (LARGE_CORPORATE, SME_CORPORATE):
            corporate correlation + maturity adjustment
          - Retail (RETAIL_RESIDENTIAL_MORTGAGE,
                    QUALIFYING_REVOLVING_RETAIL, OTHER_RETAIL):
            retail correlation + NO maturity adjustment
            (mat_factor = 1.0 per §RBC25.20)

        Backward compat: default exposure_class=LARGE_CORPORATE
        preserves the pre-v10.313 behavior for any caller that
        doesn't pass the new parameter.

        Returns (K_pct as Decimal, R, b) so caller can surface
        intermediate values per Rule 1. For retail, b is
        returned as 0.0 (no maturity adjustment used).
        """
        # PD = 1.0 (defaulted) — IRB capital = 0% above EL per §RBC25.16
        if pd >= PD_DEFAULT_CEILING:
            return (Decimal("0"), 0.0, 0.0)

        is_retail = exposure_class in _RETAIL_CLASSES

        if is_retail:
            r = self._correlation_retail(pd, exposure_class)
            b = 0.0  # No maturity adjustment for retail
            mat_factor = 1.0
        else:
            r = self._correlation(pd)
            b = self._maturity_adjustment(pd)
            mat_factor = (
                (1.0 + (m - 2.5) * b) / (1.0 - 1.5 * b))

        # Normal inverses
        n_inv_pd = self._normal.inv_cdf(pd)
        n_inv_999 = self._normal.inv_cdf(CONFIDENCE_999)

        # Bracketed expression: N((1-R)^-0.5 × N^-1(PD)
        #                          + (R/(1-R))^0.5 × N^-1(0.999))
        sqrt_one_minus_r = math.sqrt(1.0 - r)
        sqrt_r_over_one_minus_r = math.sqrt(r / (1.0 - r))
        inner = (
            n_inv_pd / sqrt_one_minus_r
            + sqrt_r_over_one_minus_r * n_inv_999
        )
        big_n = self._normal.cdf(inner)

        # Final K
        k = lgd * (big_n - pd) * mat_factor
        # Floor at zero — for very low PD with high M the formula
        # can produce slightly negative numbers due to rounding
        if k < 0:
            k = 0.0

        return (Decimal(str(k)), r, b)

    # ── Public API ────────────────────────────────────────────────────
    def compute(self, exposure: IRBExposure) -> CapitalResult:
        """Compute IRB capital + RWA + EL for a single exposure.

        v10.313: now dispatches on exposure.exposure_class
        (corporate vs retail) via _capital_requirement_pct.
        Retail classes use a different correlation formula
        and no maturity adjustment per BCBS d424 §RBC25.20-23.
        """
        k_pct, r, b = self._capital_requirement_pct(
            pd=exposure.pd, lgd=exposure.lgd,
            m=exposure.maturity_years,
            exposure_class=exposure.exposure_class)
        rwa = k_pct * RWA_MULTIPLIER * exposure.ead_kes
        el = (
            Decimal(str(exposure.pd))
            * Decimal(str(exposure.lgd))
            * exposure.ead_kes)
        return CapitalResult(
            exposure_id=exposure.exposure_id,
            exposure_class=exposure.exposure_class,
            pd=exposure.pd, lgd=exposure.lgd,
            ead_kes=exposure.ead_kes,
            maturity_years=exposure.maturity_years,
            correlation_R=r, maturity_adj_b=b,
            capital_requirement_pct=k_pct.quantize(
                Decimal("0.000001")),
            rwa_kes=rwa.quantize(Decimal("0.01")),
            expected_loss_kes=el.quantize(Decimal("0.01")),
            framework_refs=(
                "BCBS d424 §RBC25", "Basel III IRB Approach",
                "CBK PG/15 Risk Classification"),
            notes=exposure.notes)

    def compute_portfolio(
        self, exposures: List[IRBExposure],
    ) -> Tuple[Tuple[CapitalResult, ...], Decimal, Decimal]:
        """Compute IRB for a portfolio.

        Returns (per-exposure results, total RWA, total EL).
        Aggregation is simple sum — no diversification benefit at
        IRB level (that would be Pillar 2 economic capital, future
        scope).
        """
        results: List[CapitalResult] = []
        total_rwa = Decimal("0")
        total_el = Decimal("0")
        for exp in exposures:
            r = self.compute(exp)
            results.append(r)
            total_rwa += r.rwa_kes
            total_el += r.expected_loss_kes
        return (
            tuple(results),
            total_rwa.quantize(Decimal("0.01")),
            total_el.quantize(Decimal("0.01")))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_exposure_validates_pd_range():
    try:
        IRBExposure(
            exposure_id="bad", exposure_class=ExposureClass.LARGE_CORPORATE,
            pd=1.5, lgd=0.45, ead_kes=Decimal("1000000"),
            maturity_years=2.5)
        assert False
    except ValueError:
        pass


def _test_exposure_validates_lgd_range():
    try:
        IRBExposure(
            exposure_id="bad", exposure_class=ExposureClass.LARGE_CORPORATE,
            pd=0.01, lgd=1.5, ead_kes=Decimal("1000000"),
            maturity_years=2.5)
        assert False
    except ValueError:
        pass


def _test_exposure_validates_ead_positive():
    try:
        IRBExposure(
            exposure_id="bad", exposure_class=ExposureClass.LARGE_CORPORATE,
            pd=0.01, lgd=0.45, ead_kes=Decimal("0"),
            maturity_years=2.5)
        assert False
    except ValueError:
        pass


def _test_exposure_validates_maturity_range():
    try:
        IRBExposure(
            exposure_id="bad", exposure_class=ExposureClass.LARGE_CORPORATE,
            pd=0.01, lgd=0.45, ead_kes=Decimal("1000000"),
            maturity_years=0.5)
        assert False
    except ValueError:
        pass


def _test_exposure_rejects_unimplemented_class():
    try:
        IRBExposure(
            exposure_id="bad", exposure_class=ExposureClass.SOVEREIGN,
            pd=0.01, lgd=0.45, ead_kes=Decimal("1000000"),
            maturity_years=2.5)
        assert False
    except ValueError:
        pass


def _test_correlation_decreases_with_pd():
    """R(PD) should decrease as PD increases per BCBS §RBC25.7."""
    engine = IRBCapitalEngine()
    r_low = engine._correlation(0.001)
    r_med = engine._correlation(0.05)
    r_high = engine._correlation(0.5)
    assert r_low > r_med > r_high
    # Bounds: 0.12 ≤ R ≤ 0.24
    assert 0.12 <= r_high <= r_low <= 0.24


def _test_maturity_adjustment_decreases_with_pd():
    """b(PD) decreases as PD rises (high-PD loans less M-sensitive)."""
    engine = IRBCapitalEngine()
    b_low = engine._maturity_adjustment(0.001)
    b_high = engine._maturity_adjustment(0.5)
    assert b_low > b_high


def _test_defaulted_exposure_has_zero_irb_capital():
    """PD = 1.0 → IRB K = 0 above EL per §RBC25.16."""
    engine = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="defaulted",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=1.0, lgd=0.45, ead_kes=Decimal("1000000"),
        maturity_years=2.5)
    result = engine.compute(exp)
    assert result.capital_requirement_pct == Decimal("0")
    # EL = 1.0 × 0.45 × 1m = 450,000
    assert result.expected_loss_kes == Decimal("450000.00")


def _test_typical_corporate_capital():
    """PD=1%, LGD=45%, M=2.5 — should produce a sensible K (~6-8%)."""
    engine = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="typical",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=0.01, lgd=0.45, ead_kes=Decimal("10000000"),
        maturity_years=2.5)
    result = engine.compute(exp)
    # Sanity: 4% < K < 12% for typical corporate
    k = float(result.capital_requirement_pct)
    assert 0.04 < k < 0.12, f"K={k} outside expected range"


def _test_rwa_equals_k_times_125_times_ead():
    """RWA = K × 12.5 × EAD identity (within rounding tolerance)."""
    engine = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="rwa_test",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=0.02, lgd=0.40, ead_kes=Decimal("5000000"),
        maturity_years=3.0)
    result = engine.compute(exp)
    expected_rwa = (
        result.capital_requirement_pct
        * Decimal("12.5")
        * exp.ead_kes).quantize(Decimal("0.01"))
    # Tolerance accounts for K being quantized to 6dp before
    # this test recomputes RWA. Real RWA uses full-precision K.
    diff = abs(result.rwa_kes - expected_rwa)
    assert diff < Decimal("100"), (
        f"RWA {result.rwa_kes} too far from K×12.5×EAD "
        f"{expected_rwa} (diff {diff})")


def _test_expected_loss_is_pd_times_lgd_times_ead():
    engine = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="el_test",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=0.05, lgd=0.50, ead_kes=Decimal("2000000"),
        maturity_years=2.5)
    result = engine.compute(exp)
    # EL = 0.05 × 0.50 × 2m = 50,000
    assert result.expected_loss_kes == Decimal("50000.00")


def _test_higher_pd_higher_capital():
    """Holding LGD/EAD/M constant, K should rise with PD."""
    engine = IRBCapitalEngine()
    base = dict(
        exposure_class=ExposureClass.LARGE_CORPORATE,
        lgd=0.45, ead_kes=Decimal("1000000"), maturity_years=2.5)
    low = engine.compute(IRBExposure(
        exposure_id="low", pd=0.005, **base))
    high = engine.compute(IRBExposure(
        exposure_id="high", pd=0.10, **base))
    assert (high.capital_requirement_pct
            > low.capital_requirement_pct)


def _test_higher_maturity_higher_capital():
    """M=5 > M=1 → higher K (maturity adjustment factor)."""
    engine = IRBCapitalEngine()
    base = dict(
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=0.02, lgd=0.45, ead_kes=Decimal("1000000"))
    short = engine.compute(IRBExposure(
        exposure_id="short", maturity_years=1.0, **base))
    long_ = engine.compute(IRBExposure(
        exposure_id="long", maturity_years=5.0, **base))
    assert (long_.capital_requirement_pct
            > short.capital_requirement_pct)


def _test_capital_result_has_full_provenance():
    engine = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="prov",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=0.01, lgd=0.45, ead_kes=Decimal("1000000"),
        maturity_years=2.5)
    r = engine.compute(exp)
    assert r.correlation_R > 0
    assert r.maturity_adj_b > 0
    assert len(r.framework_refs) >= 2
    assert "BCBS d424" in r.framework_refs[0]


def _test_portfolio_aggregates_rwa_and_el():
    engine = IRBCapitalEngine()
    exposures = [
        IRBExposure(
            exposure_id=f"e{i}",
            exposure_class=ExposureClass.LARGE_CORPORATE,
            pd=0.01 * (i + 1), lgd=0.45,
            ead_kes=Decimal("1000000"),
            maturity_years=2.5)
        for i in range(3)]
    results, total_rwa, total_el = (
        engine.compute_portfolio(exposures))
    assert len(results) == 3
    sum_rwa = sum(
        (r.rwa_kes for r in results), Decimal("0"))
    sum_el = sum(
        (r.expected_loss_kes for r in results), Decimal("0"))
    assert total_rwa == sum_rwa.quantize(Decimal("0.01"))
    assert total_el == sum_el.quantize(Decimal("0.01"))


def _test_pd_floor_enforced():
    """PD below floor should be rejected at construction."""
    try:
        IRBExposure(
            exposure_id="below_floor",
            exposure_class=ExposureClass.LARGE_CORPORATE,
            pd=0.0001, lgd=0.45, ead_kes=Decimal("1000000"),
            maturity_years=2.5)
        assert False
    except ValueError:
        pass


def self_test() -> None:
    tests = [
        _test_exposure_validates_pd_range,
        _test_exposure_validates_lgd_range,
        _test_exposure_validates_ead_positive,
        _test_exposure_validates_maturity_range,
        _test_exposure_rejects_unimplemented_class,
        _test_correlation_decreases_with_pd,
        _test_maturity_adjustment_decreases_with_pd,
        _test_defaulted_exposure_has_zero_irb_capital,
        _test_typical_corporate_capital,
        _test_rwa_equals_k_times_125_times_ead,
        _test_expected_loss_is_pd_times_lgd_times_ead,
        _test_higher_pd_higher_capital,
        _test_higher_maturity_higher_capital,
        _test_capital_result_has_full_provenance,
        _test_portfolio_aggregates_rwa_and_el,
        _test_pd_floor_enforced,
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
            f"✗ credit_risk_irb self-test: {len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ credit_risk_irb self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

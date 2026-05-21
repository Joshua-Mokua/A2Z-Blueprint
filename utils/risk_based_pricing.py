"""utils/risk_based_pricing.py — v10.13 Phase 2 deep impl batch 7 (Credit batch 3 part 1).

╔════════════════════════════════════════════════════════════════════════╗
║  RISK-BASED PRICING — RATE COMPONENTS + RAROC + PRICING DECISION       ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (rate determination affects revenue + customer)    ║
║  Implements 1 of 19 Credit standards from registry:                     ║
║    ENH-123: Dynamic Risk-Based Pricing                                  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Methodology:                                                            ║
║    Required Rate =                                                      ║
║         Funding Cost                                                    ║
║       + Expected Loss / EAD                                             ║
║       + (Capital Charge × Cost of Capital) / EAD                       ║
║       + Operating Cost (% of EAD)                                       ║
║       + Target Margin                                                   ║
║                                                                         ║
║    RAROC = (Revenue - Funding - EL - OpEx) / Capital_Held              ║
║                                                                         ║
║  Capital charge K computed via Basel IRB simplified formula:           ║
║    K = LGD × N(... PD-correlation-adjusted ...) - PD × LGD             ║
║    For our purposes the platform uses a deterministic linear           ║
║    approximation calibrated to Basel IRB outputs across PD ranges.     ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel III IRB framework (BCBS 128 / BCBS 424)                       ║
║    CBK Prudential Guideline CBK/PG/03 — capital adequacy               ║
║    CBK Banking Act §44 — interest rate disclosure                       ║
║    Truth in Lending Act (US analog) Reg Z 12 CFR §1026.18              ║
║                                                                         ║
║  Composes with: utils/ai_underwriting.py (v10.11) — PD/LGD/EAD inputs  ║
║                  utils/credit_risk_scoring.py — Basel IRB foundation   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

# ════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════

# Default capital ratio target — Basel III + CBK PG/03 add-on
DEFAULT_CAPITAL_RATIO_TARGET = Decimal("0.14")     # 14% (10.5% Basel + 3.5% buffer)

# Cost of equity for capital charge (illustrative; bank-specific)
DEFAULT_COST_OF_EQUITY = Decimal("0.18")           # 18% per annum

# Operating cost as % of EAD (illustrative)
DEFAULT_OPEX_PCT_OF_EAD = Decimal("0.015")         # 1.5%

# Target margin (illustrative)
DEFAULT_TARGET_MARGIN = Decimal("0.03")            # 3%

# Floor + ceiling for rate (regulatory + market constraints)
RATE_FLOOR = Decimal("0.06")     # 6% — below this, deal makes no economic sense
RATE_CEILING = Decimal("0.32")   # 32% — Kenya consumer lending soft cap (CBK guidance)


# ════════════════════════════════════════════════════════════════════════
# Pricing decision categories
# ════════════════════════════════════════════════════════════════════════

class PricingDecision(Enum):
    """Outcome of pricing computation."""
    PRICE_OFFERED = "PRICE_OFFERED"
    PRICE_AT_FLOOR = "PRICE_AT_FLOOR"        # required rate < floor → offer floor
    PRICE_AT_CEILING = "PRICE_AT_CEILING"    # required rate > ceiling → offer ceiling
    DECLINE_UNECONOMIC = "DECLINE_UNECONOMIC"  # required rate too high — likely better declined
    REFER_HUMAN = "REFER_HUMAN"              # PD/LGD/EAD missing or implausible


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PricingInputs:
    """Inputs needed to compute a risk-based rate."""
    asset_id: str
    pd: Decimal              # 12m or lifetime — pricing horizon-matched
    lgd: Decimal             # [0, 1]
    ead_kes: Decimal
    tenor_months: int
    funding_rate: Decimal    # bank's marginal funding rate (annualized)
    opex_pct: Optional[Decimal] = None
    target_margin: Optional[Decimal] = None
    cost_of_equity: Optional[Decimal] = None
    capital_ratio: Optional[Decimal] = None
    rate_floor: Optional[Decimal] = None
    rate_ceiling: Optional[Decimal] = None
    notes: str = ""

    def __post_init__(self):
        if not (Decimal("0") <= self.pd <= Decimal("1")):
            raise ValueError(f"pd {self.pd} outside [0, 1]")
        if not (Decimal("0") <= self.lgd <= Decimal("1")):
            raise ValueError(f"lgd {self.lgd} outside [0, 1]")
        if self.ead_kes <= Decimal("0"):
            raise ValueError(f"ead_kes {self.ead_kes} must be > 0")
        if self.tenor_months < 1:
            raise ValueError(f"tenor_months {self.tenor_months} must be ≥ 1")
        if self.funding_rate < Decimal("0"):
            raise ValueError(
                f"funding_rate {self.funding_rate} cannot be negative")


@dataclass(frozen=True)
class PricingComponents:
    """Decomposed rate components (annualized, expressed as decimal fractions)."""
    funding_cost: Decimal
    expected_loss_pct: Decimal       # PD × LGD
    capital_charge_pct: Decimal      # K × cost_of_equity
    opex_pct: Decimal
    target_margin: Decimal
    required_rate: Decimal           # sum of above
    notes: str = ""


@dataclass(frozen=True)
class PricingResult:
    """Pricing decision + offered rate + components + RAROC."""
    asset_id: str
    decision: PricingDecision
    required_rate: Decimal           # pre-floor/ceiling cap
    offered_rate: Decimal            # what we actually quote
    components: PricingComponents
    raroc: Optional[Decimal]         # at offered rate
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Capital charge — Basel IRB simplified
# ════════════════════════════════════════════════════════════════════════

# Linear approximation table for Basel IRB K formula
# (PD bucket → capital factor as % of LGD × EAD)
# Sourced from Basel BCBS 128 IRB Foundation supervisory formula
# evaluated at LGD=0.45, M=2.5y for typical retail/SME exposures.
_IRB_K_TABLE: Tuple[Tuple[Decimal, Decimal], ...] = (
    (Decimal("0.0001"), Decimal("0.005")),
    (Decimal("0.0010"), Decimal("0.012")),
    (Decimal("0.0050"), Decimal("0.030")),
    (Decimal("0.0100"), Decimal("0.045")),
    (Decimal("0.0200"), Decimal("0.065")),
    (Decimal("0.0500"), Decimal("0.090")),
    (Decimal("0.1000"), Decimal("0.115")),
    (Decimal("0.2000"), Decimal("0.140")),
    (Decimal("0.5000"), Decimal("0.180")),
    (Decimal("1.0000"), Decimal("0.220")),
)


def basel_irb_capital_factor(pd: Decimal) -> Decimal:
    """Look up Basel IRB capital factor K (% of EAD × LGD) for a PD.

    Linear interpolation between table points. Capped at table extremes.
    """
    if pd <= _IRB_K_TABLE[0][0]:
        return _IRB_K_TABLE[0][1]
    if pd >= _IRB_K_TABLE[-1][0]:
        return _IRB_K_TABLE[-1][1]
    for i in range(len(_IRB_K_TABLE) - 1):
        pd_lo, k_lo = _IRB_K_TABLE[i]
        pd_hi, k_hi = _IRB_K_TABLE[i + 1]
        if pd_lo <= pd <= pd_hi:
            # Linear interp
            frac = (pd - pd_lo) / (pd_hi - pd_lo)
            return k_lo + frac * (k_hi - k_lo)
    return _IRB_K_TABLE[-1][1]


# ════════════════════════════════════════════════════════════════════════
# Rate computation
# ════════════════════════════════════════════════════════════════════════

def compute_pricing_components(inputs: PricingInputs) -> PricingComponents:
    """Decompose required rate into its 5 components.

    funding_cost     = inputs.funding_rate
    expected_loss    = pd × lgd
    capital_charge   = K × LGD × cost_of_equity / 1.0  (per EAD)
                       where K from Basel IRB table
    opex             = inputs.opex_pct or DEFAULT_OPEX_PCT_OF_EAD
    target_margin    = inputs.target_margin or DEFAULT_TARGET_MARGIN
    required_rate    = sum
    """
    opex = inputs.opex_pct or DEFAULT_OPEX_PCT_OF_EAD
    margin = inputs.target_margin or DEFAULT_TARGET_MARGIN
    coe = inputs.cost_of_equity or DEFAULT_COST_OF_EQUITY

    expected_loss = inputs.pd * inputs.lgd

    k = basel_irb_capital_factor(inputs.pd)
    # Capital charge per unit EAD = K × LGD × cost_of_equity
    # (K already expressed as % of EAD × LGD; we re-multiply to get ratio)
    capital_charge = k * inputs.lgd * coe

    required = (
        inputs.funding_rate
        + expected_loss
        + capital_charge
        + opex
        + margin)

    return PricingComponents(
        funding_cost=inputs.funding_rate,
        expected_loss_pct=expected_loss,
        capital_charge_pct=capital_charge,
        opex_pct=opex,
        target_margin=margin,
        required_rate=required,
        notes=f"K={k} (Basel IRB lookup at PD={inputs.pd})")


def price_loan(inputs: PricingInputs) -> PricingResult:
    """Compute pricing + decision for a loan request."""
    components = compute_pricing_components(inputs)
    required = components.required_rate

    floor = inputs.rate_floor if inputs.rate_floor is not None else RATE_FLOOR
    ceiling = (
        inputs.rate_ceiling
        if inputs.rate_ceiling is not None else RATE_CEILING)

    # Decline-uneconomic threshold: required rate exceeds ceiling by 50%+
    decline_threshold = ceiling * Decimal("1.5")
    if required > decline_threshold:
        return PricingResult(
            asset_id=inputs.asset_id,
            decision=PricingDecision.DECLINE_UNECONOMIC,
            required_rate=required,
            offered_rate=ceiling,
            components=components,
            raroc=None,
            notes=(
                f"required rate {required:.4f} exceeds ceiling "
                f"{ceiling:.4f} by >50% — decline more economic than price"))

    if required > ceiling:
        offered = ceiling
        decision = PricingDecision.PRICE_AT_CEILING
    elif required < floor:
        offered = floor
        decision = PricingDecision.PRICE_AT_FLOOR
    else:
        offered = required
        decision = PricingDecision.PRICE_OFFERED

    raroc = compute_raroc(
        offered_rate=offered,
        funding_rate=inputs.funding_rate,
        expected_loss_pct=components.expected_loss_pct,
        opex_pct=components.opex_pct,
        capital_ratio=(
            inputs.capital_ratio or DEFAULT_CAPITAL_RATIO_TARGET))

    return PricingResult(
        asset_id=inputs.asset_id,
        decision=decision,
        required_rate=required,
        offered_rate=offered,
        components=components,
        raroc=raroc,
        notes=f"Basel IRB K={basel_irb_capital_factor(inputs.pd)}")


def compute_raroc(
    *,
    offered_rate: Decimal,
    funding_rate: Decimal,
    expected_loss_pct: Decimal,
    opex_pct: Decimal,
    capital_ratio: Decimal,
) -> Decimal:
    """Risk-Adjusted Return on Capital (RAROC).

    RAROC = (revenue_pct - funding_pct - EL_pct - opex_pct) / capital_ratio

    All inputs as decimal fractions of EAD.
    """
    if capital_ratio <= Decimal("0"):
        raise ValueError(f"capital_ratio {capital_ratio} must be > 0")
    risk_adjusted_margin = (
        offered_rate - funding_rate - expected_loss_pct - opex_pct)
    return risk_adjusted_margin / capital_ratio


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_irb_k_lookup_extremes():
    """K lookup returns table extremes for very low/high PD."""
    assert basel_irb_capital_factor(Decimal("0")) == _IRB_K_TABLE[0][1]
    assert basel_irb_capital_factor(Decimal("1")) == _IRB_K_TABLE[-1][1]


def _test_irb_k_lookup_interpolates():
    """K lookup interpolates linearly between table points."""
    # Between PD=0.05 (K=0.090) and PD=0.10 (K=0.115)
    # At PD=0.075 → midpoint → K ≈ 0.1025
    k = basel_irb_capital_factor(Decimal("0.075"))
    assert Decimal("0.10") < k < Decimal("0.11")


def _test_irb_k_monotonic():
    """K is monotone non-decreasing in PD."""
    pds = [Decimal(str(p)) for p in [0.001, 0.01, 0.05, 0.10, 0.30, 0.70]]
    ks = [basel_irb_capital_factor(p) for p in pds]
    for i in range(len(ks) - 1):
        assert ks[i] <= ks[i + 1], f"K not monotone: {ks}"


def _test_pricing_inputs_validation():
    """PricingInputs rejects invalid PD/LGD/EAD/tenor."""
    valid = dict(
        asset_id="L", pd=Decimal("0.02"), lgd=Decimal("0.45"),
        ead_kes=Decimal("1000000"), tenor_months=12,
        funding_rate=Decimal("0.10"))
    PricingInputs(**valid)  # ok

    try:
        PricingInputs(**{**valid, "pd": Decimal("1.5")})
        assert False
    except ValueError as e:
        assert "pd" in str(e)

    try:
        PricingInputs(**{**valid, "ead_kes": Decimal("-1")})
        assert False
    except ValueError as e:
        assert "ead_kes" in str(e)


def _test_pricing_components_sum():
    """Required rate = sum of 5 components."""
    inputs = PricingInputs(
        asset_id="L", pd=Decimal("0.02"), lgd=Decimal("0.45"),
        ead_kes=Decimal("1000000"), tenor_months=12,
        funding_rate=Decimal("0.10"))
    c = compute_pricing_components(inputs)
    expected = (
        c.funding_cost + c.expected_loss_pct + c.capital_charge_pct
        + c.opex_pct + c.target_margin)
    assert c.required_rate == expected


def _test_pricing_low_risk_offered():
    """Low-risk loan → PRICE_OFFERED in normal band."""
    inputs = PricingInputs(
        asset_id="L", pd=Decimal("0.01"), lgd=Decimal("0.40"),
        ead_kes=Decimal("1000000"), tenor_months=12,
        funding_rate=Decimal("0.08"))
    r = price_loan(inputs)
    assert r.decision == PricingDecision.PRICE_OFFERED
    assert RATE_FLOOR <= r.offered_rate <= RATE_CEILING


def _test_pricing_high_risk_at_ceiling():
    """High PD pushes required rate to ceiling."""
    inputs = PricingInputs(
        asset_id="L", pd=Decimal("0.50"), lgd=Decimal("0.50"),
        ead_kes=Decimal("100000"), tenor_months=12,
        funding_rate=Decimal("0.10"))
    r = price_loan(inputs)
    # PD=0.50, LGD=0.50 → EL alone = 25%; plus 10% funding etc → required ≈ 41%
    # That's > ceiling (32%) but < decline_threshold (48%)
    assert r.required_rate > RATE_CEILING
    assert r.decision == PricingDecision.PRICE_AT_CEILING


def _test_pricing_extreme_risk_declines():
    """Very high required rate → DECLINE_UNECONOMIC."""
    inputs = PricingInputs(
        asset_id="L", pd=Decimal("0.80"), lgd=Decimal("0.90"),
        ead_kes=Decimal("100000"), tenor_months=12,
        funding_rate=Decimal("0.15"))
    r = price_loan(inputs)
    # PD=0.80, LGD=0.90 → EL=72% alone → required > 80% > ceiling × 1.5
    assert r.decision == PricingDecision.DECLINE_UNECONOMIC


def _test_pricing_below_floor_priced_at_floor():
    """Required rate < floor (e.g., very low PD + low cost) → PRICE_AT_FLOOR."""
    inputs = PricingInputs(
        asset_id="L", pd=Decimal("0.0001"), lgd=Decimal("0.10"),
        ead_kes=Decimal("10000000"), tenor_months=12,
        funding_rate=Decimal("0.005"),
        opex_pct=Decimal("0.005"),
        target_margin=Decimal("0.005"))
    r = price_loan(inputs)
    assert r.required_rate < RATE_FLOOR
    assert r.decision == PricingDecision.PRICE_AT_FLOOR
    assert r.offered_rate == RATE_FLOOR


def _test_raroc_positive_for_priced_loan():
    """Loan offered at required rate has positive RAROC."""
    inputs = PricingInputs(
        asset_id="L", pd=Decimal("0.02"), lgd=Decimal("0.40"),
        ead_kes=Decimal("1000000"), tenor_months=12,
        funding_rate=Decimal("0.08"))
    r = price_loan(inputs)
    assert r.raroc is not None
    assert r.raroc > Decimal("0")


def _test_raroc_capital_ratio_zero_raises():
    try:
        compute_raroc(
            offered_rate=Decimal("0.15"),
            funding_rate=Decimal("0.10"),
            expected_loss_pct=Decimal("0.01"),
            opex_pct=Decimal("0.02"),
            capital_ratio=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_decimal_purity():
    inputs = PricingInputs(
        asset_id="L", pd=Decimal("0.02"), lgd=Decimal("0.45"),
        ead_kes=Decimal("1000000"), tenor_months=12,
        funding_rate=Decimal("0.10"))
    r = price_loan(inputs)
    assert isinstance(r.required_rate, Decimal)
    assert isinstance(r.offered_rate, Decimal)
    assert isinstance(r.raroc, Decimal)


def self_test() -> None:
    tests = [
        _test_irb_k_lookup_extremes,
        _test_irb_k_lookup_interpolates,
        _test_irb_k_monotonic,
        _test_pricing_inputs_validation,
        _test_pricing_components_sum,
        _test_pricing_low_risk_offered,
        _test_pricing_high_risk_at_ceiling,
        _test_pricing_extreme_risk_declines,
        _test_pricing_below_floor_priced_at_floor,
        _test_raroc_positive_for_priced_loan,
        _test_raroc_capital_ratio_zero_raises,
        _test_decimal_purity,
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
        print(f"✗ risk_based_pricing self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ risk_based_pricing self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

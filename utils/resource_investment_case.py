"""utils.resource_investment_case — Resource Investment Case
Generator (ENH-163, v10.187).

Phase 5 Resource Optimization — eighth standard. Turns a
baseline + alternative scenario projection (from ENH-162) plus
caller-supplied cost assumptions into a board-ready investment
case: NPV, payback period, IRR (when computable), annual cash
flows, and an explicit list of qualitative benefits that were
NOT monetised.

DESIGN CONTRACT
---------------
1. **Inputs are explicit costs and benefits.** Engine does NOT
   guess salary levels or office reconfiguration costs from
   training data. The caller passes a `CostAssumptions` record
   with annual_cost_per_fte, one_time_implementation_cost, and
   any qualitative_benefits text. Engine refuses defaults that
   could become hidden.
2. **NPV uses standard DCF math.** No proprietary discounting
   tricks. Discount rate is caller-supplied. We document the
   formula in the engine docstring and in `board_summary()`.
3. **Payback period is undiscounted by default.** A separate
   `discounted_payback_years` field is also produced. Both are
   reported.
4. **Revenue upside is OUT OF SCOPE.** SL improvement could
   plausibly drive customer retention / upsell; we do NOT model
   that side. `REVENUE_UPSIDE_FROM_SL` is named in deferrals.
   The case is a cost-side analysis only.
5. **Qualitative benefits surface as text, never as fabricated
   numbers.** Wellbeing improvement, attrition reduction,
   employer-brand effect — all listed as qualitative benefits
   that the operator can manually monetise if they have data,
   but the engine refuses to invent values.
6. **No revenue, no recommendation.** Engine produces an
   InvestmentCase record with the math. It does NOT output
   APPROVE / REJECT — that's a human / committee decision.

REGULATORY BASIS
----------------
- Internal Capital Allocation Policy
- BSC Financial perspective (cost discipline)
- BSC People perspective (qualitative benefits anchor)

HONEST DEFERRALS
----------------
- DETAILED_TAX_TREATMENT: ignores tax shield on labour costs;
  pre-tax cash flows only
- INFLATION_INDEXATION: constant nominal salaries assumed across
  the horizon; no salary escalator
- REVENUE_UPSIDE_FROM_SL: engine quantifies cost side only; SL-
  driven retention / upsell value is qualitative
- MULTI_YEAR_RAMP: assumes steady-state cost structure from year
  1; no headcount ramp curve
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# Reasonable bounds for sanity (engine refuses out-of-bounds)
MIN_DISCOUNT_RATE = 0.0
MAX_DISCOUNT_RATE = 1.0  # 100% — anything above is a typo
MIN_HORIZON_YEARS = 1
MAX_HORIZON_YEARS = 30


@dataclass(frozen=True)
class CostAssumptions:
    """Caller-supplied cost inputs.

    Engine refuses to default any of these — operator MUST
    declare them explicitly.
    """
    annual_cost_per_fte: float            # all-in (salary + benefits + ops)
    one_time_implementation_cost: float   # office reconfig, tech setup, etc.
    discount_rate: float                  # decimal, e.g. 0.12 for 12%
    horizon_years: int                    # analysis horizon
    annual_other_costs: float = 0.0       # licenses, vendor fees, etc.
    qualitative_benefits: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "annual_cost_per_fte": self.annual_cost_per_fte,
            "one_time_implementation_cost": (
                self.one_time_implementation_cost
            ),
            "discount_rate": self.discount_rate,
            "horizon_years": self.horizon_years,
            "annual_other_costs": self.annual_other_costs,
            "qualitative_benefits": list(self.qualitative_benefits),
        }


@dataclass(frozen=True)
class AnnualCashFlow:
    """One year of the cash flow series."""
    year: int  # 1..horizon
    nominal_cash_flow: float       # positive = saving
    discounted_cash_flow: float
    cumulative_nominal: float
    cumulative_discounted: float


@dataclass(frozen=True)
class InvestmentCase:
    """The full investment case package."""
    case_id: str
    baseline_scenario_id: str
    alternative_scenario_id: str
    baseline_effective_fte: float
    alternative_effective_fte: float
    annual_fte_delta: float            # alt - base (positive = more FTE)
    annual_labour_cost_delta: float    # cost change per year (- = saving)
    annual_other_cost_delta: float     # in alt assumptions only
    annual_net_cash_flow: float        # the per-year saving (negative if more cost)
    one_time_implementation_cost: float
    discount_rate: float
    horizon_years: int
    npv: float
    payback_years_undiscounted: Optional[float]
    payback_years_discounted: Optional[float]
    irr: Optional[float]
    annual_cash_flows: Tuple[AnnualCashFlow, ...]
    qualitative_benefits: Tuple[str, ...]
    deferrals_acknowledged: Tuple[str, ...]
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "baseline_scenario_id": self.baseline_scenario_id,
            "alternative_scenario_id": self.alternative_scenario_id,
            "baseline_effective_fte": self.baseline_effective_fte,
            "alternative_effective_fte": self.alternative_effective_fte,
            "annual_fte_delta": self.annual_fte_delta,
            "annual_labour_cost_delta": self.annual_labour_cost_delta,
            "annual_other_cost_delta": self.annual_other_cost_delta,
            "annual_net_cash_flow": self.annual_net_cash_flow,
            "one_time_implementation_cost": (
                self.one_time_implementation_cost
            ),
            "discount_rate": self.discount_rate,
            "horizon_years": self.horizon_years,
            "npv": self.npv,
            "payback_years_undiscounted": (
                self.payback_years_undiscounted
            ),
            "payback_years_discounted": self.payback_years_discounted,
            "irr": self.irr,
            "annual_cash_flows": [
                {
                    "year": cf.year,
                    "nominal_cash_flow": cf.nominal_cash_flow,
                    "discounted_cash_flow": cf.discounted_cash_flow,
                    "cumulative_nominal": cf.cumulative_nominal,
                    "cumulative_discounted": cf.cumulative_discounted,
                }
                for cf in self.annual_cash_flows
            ],
            "qualitative_benefits": list(self.qualitative_benefits),
            "deferrals_acknowledged": list(self.deferrals_acknowledged),
            "generated_at": self.generated_at,
        }


class ResourceInvestmentCaseEngine:
    """Generates investment cases from scenario projections."""

    DEFERRALS = (
        "DETAILED_TAX_TREATMENT",
        "INFLATION_INDEXATION",
        "REVENUE_UPSIDE_FROM_SL",
        "MULTI_YEAR_RAMP",
    )

    def __init__(self):
        self._cases: List[InvestmentCase] = []

    # ---------------------------------------------- validation

    @staticmethod
    def _validate_assumptions(a: CostAssumptions) -> None:
        if a.annual_cost_per_fte < 0:
            raise ValueError("annual_cost_per_fte must be non-negative")
        if a.one_time_implementation_cost < 0:
            raise ValueError(
                "one_time_implementation_cost must be non-negative"
            )
        if a.annual_other_costs < 0:
            raise ValueError("annual_other_costs must be non-negative")
        if not (MIN_DISCOUNT_RATE <= a.discount_rate
                <= MAX_DISCOUNT_RATE):
            raise ValueError(
                f"discount_rate must be in "
                f"[{MIN_DISCOUNT_RATE}, {MAX_DISCOUNT_RATE}]; "
                f"got {a.discount_rate}"
            )
        if not (MIN_HORIZON_YEARS <= a.horizon_years
                <= MAX_HORIZON_YEARS):
            raise ValueError(
                f"horizon_years must be in "
                f"[{MIN_HORIZON_YEARS}, {MAX_HORIZON_YEARS}]; "
                f"got {a.horizon_years}"
            )

    # ----------------------------------------------------- math

    @staticmethod
    def _npv(
        cash_flows: List[float],
        rate: float,
        one_time: float,
    ) -> float:
        """NPV with discounting starting at year 1.

        NPV = -one_time + sum_{t=1..N} CF_t / (1+r)^t
        """
        total = -one_time
        for t, cf in enumerate(cash_flows, start=1):
            total += cf / ((1 + rate) ** t)
        return total

    @staticmethod
    def _payback(
        annual_net: float, one_time: float
    ) -> Optional[float]:
        """Undiscounted payback (years).

        Returns None if annual_net <= 0 (no payback).
        """
        if annual_net <= 0 or one_time <= 0:
            return None
        return one_time / annual_net

    @staticmethod
    def _discounted_payback(
        cash_flows: List[float], rate: float, one_time: float,
    ) -> Optional[float]:
        """Discounted payback. Returns None if never recouped."""
        if one_time <= 0:
            return 0.0
        cumulative = -one_time
        for t, cf in enumerate(cash_flows, start=1):
            disc_cf = cf / ((1 + rate) ** t)
            prev = cumulative
            cumulative += disc_cf
            if cumulative >= 0:
                # Linear interpolation within year t
                if disc_cf <= 0:
                    return float(t)
                fraction_into_year = -prev / disc_cf
                return (t - 1) + fraction_into_year
        return None

    @staticmethod
    def _irr(
        cash_flows: List[float], one_time: float,
        max_iter: int = 100, tol: float = 1e-7,
    ) -> Optional[float]:
        """IRR via bisection on [-0.999, 5.0]. Returns None if
        no sign change in NPV across the bracket."""
        def npv_at(r):
            v = -one_time
            for t, cf in enumerate(cash_flows, start=1):
                v += cf / ((1 + r) ** t)
            return v

        lo, hi = -0.999, 5.0
        f_lo, f_hi = npv_at(lo), npv_at(hi)
        if f_lo * f_hi > 0:
            return None
        for _ in range(max_iter):
            mid = (lo + hi) / 2
            f_mid = npv_at(mid)
            if abs(f_mid) < tol:
                return mid
            if f_lo * f_mid < 0:
                hi, f_hi = mid, f_mid
            else:
                lo, f_lo = mid, f_mid
        return (lo + hi) / 2

    # --------------------------------------------- generation

    def generate_case(
        self,
        case_id: str,
        baseline_projection: Any,
        alternative_projection: Any,
        cost_assumptions: CostAssumptions,
    ) -> InvestmentCase:
        """Build investment case comparing baseline to alternative.

        baseline_projection / alternative_projection are
        ScenarioProjection records from ENH-162. Engine reads
        only `aggregate_effective_headcount` and
        `scenario_id` — duck-typed so test stubs work.
        """
        if not case_id:
            raise ValueError("case_id required")
        self._validate_assumptions(cost_assumptions)

        base_fte = float(baseline_projection.aggregate_effective_headcount)
        alt_fte = float(alternative_projection.aggregate_effective_headcount)
        fte_delta = alt_fte - base_fte
        labour_cost_delta = (
            fte_delta * cost_assumptions.annual_cost_per_fte
        )
        other_cost_delta = cost_assumptions.annual_other_costs

        # Convention: positive net cash flow = annual saving
        # If alternative has FEWER FTEs, labour_cost_delta is
        # negative, so saving = -labour_cost_delta
        annual_net = -labour_cost_delta - other_cost_delta

        # Build cash-flow series (constant annual_net for now —
        # MULTI_YEAR_RAMP deferred)
        flows = [annual_net] * cost_assumptions.horizon_years
        npv = self._npv(
            flows, cost_assumptions.discount_rate,
            cost_assumptions.one_time_implementation_cost,
        )
        payback_undisc = self._payback(
            annual_net,
            cost_assumptions.one_time_implementation_cost,
        )
        payback_disc = self._discounted_payback(
            flows, cost_assumptions.discount_rate,
            cost_assumptions.one_time_implementation_cost,
        )
        irr = self._irr(
            flows, cost_assumptions.one_time_implementation_cost,
        )

        # Build per-year cash-flow records with cumulatives
        annual_records: List[AnnualCashFlow] = []
        cum_nom = -cost_assumptions.one_time_implementation_cost
        cum_disc = -cost_assumptions.one_time_implementation_cost
        for t, cf in enumerate(flows, start=1):
            disc = cf / ((1 + cost_assumptions.discount_rate) ** t)
            cum_nom += cf
            cum_disc += disc
            annual_records.append(AnnualCashFlow(
                year=t,
                nominal_cash_flow=cf,
                discounted_cash_flow=disc,
                cumulative_nominal=cum_nom,
                cumulative_discounted=cum_disc,
            ))

        case = InvestmentCase(
            case_id=case_id,
            baseline_scenario_id=baseline_projection.scenario_id,
            alternative_scenario_id=(
                alternative_projection.scenario_id
            ),
            baseline_effective_fte=base_fte,
            alternative_effective_fte=alt_fte,
            annual_fte_delta=fte_delta,
            annual_labour_cost_delta=labour_cost_delta,
            annual_other_cost_delta=other_cost_delta,
            annual_net_cash_flow=annual_net,
            one_time_implementation_cost=(
                cost_assumptions.one_time_implementation_cost
            ),
            discount_rate=cost_assumptions.discount_rate,
            horizon_years=cost_assumptions.horizon_years,
            npv=npv,
            payback_years_undiscounted=payback_undisc,
            payback_years_discounted=payback_disc,
            irr=irr,
            annual_cash_flows=tuple(annual_records),
            qualitative_benefits=cost_assumptions.qualitative_benefits,
            deferrals_acknowledged=self.DEFERRALS,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._cases.append(case)
        return case

    # ------------------------------------------------- queries

    def list_cases(self) -> List[InvestmentCase]:
        return list(self._cases)

    # ----------------------------------------------------- meta

    def board_summary(self) -> Dict[str, Any]:
        positive_npv = [c for c in self._cases if c.npv > 0]
        return {
            "engine": "ENH-163 ResourceInvestmentCaseEngine",
            "n_cases_lifetime": len(self._cases),
            "n_cases_with_positive_npv": len(positive_npv),
            "n_cases_with_finite_payback": len([
                c for c in self._cases
                if c.payback_years_undiscounted is not None
            ]),
            "regulatory_basis": (
                "Internal Capital Allocation Policy + "
                "BSC Financial perspective + "
                "BSC People perspective"
            ),
            "npv_formula": (
                "NPV = -one_time + Σ_{t=1..N} CF_t / (1+r)^t"
            ),
            "deferrals": {
                "DETAILED_TAX_TREATMENT": (
                    "DEFERRED — ignores tax shield on labour "
                    "costs; pre-tax cash flows only"
                ),
                "INFLATION_INDEXATION": (
                    "DEFERRED — constant nominal salaries; no "
                    "salary escalator across horizon"
                ),
                "REVENUE_UPSIDE_FROM_SL": (
                    "DEFERRED — cost-side analysis only; SL-"
                    "driven retention/upsell value qualitative"
                ),
                "MULTI_YEAR_RAMP": (
                    "DEFERRED — steady-state cost structure "
                    "assumed from year 1; no ramp curve"
                ),
            },
        }

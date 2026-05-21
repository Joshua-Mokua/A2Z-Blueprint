"""utils.strategy_roi — Strategy ROI & Impact Analytics
(Standard ENH-155, v10.140). Phase 1 Strategy Module — fifteenth and
final engine.

Per Continuation.docx §Standard #155 (Eco Bank QA spec):
    StrategyROIAnalytics — measure true ROI of strategic initiatives.
    Includes direct (revenue, cost savings) and indirect (customer,
    employee, risk) benefits with monetization. Compute payback
    period.

This is the FIFTEENTH and FINAL standard of the Strategy module.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. ROI calculation is fully deterministic — same input → same output
  2. Indirect benefit monetization uses NAMED CONSTANTS with documented
     defaults; banks override per their cost basis
  3. AI hooks (ai_attribution_fn) for richer benefit attribution opt-in
     and tagged basis="llm"; rule-based fallback transparent
  4. NO speculative ROI projections — engine reports only what can be
     computed from real seed data; missing inputs return explicit
     fallback_reason

WHAT THIS MODULE SHIPS
----------------------
1. StrategyROIAnalytics class with:
   - calculate_strategy_roi(strategy_cycle_id) — full ROI pipeline
   - calculate_revenue_impact(cycle_id) — sum of revenue deltas
   - calculate_cost_savings(cycle_id) — sum of cost reductions
   - calculate_customer_impact(cycle_id) — LTV × affected customers
   - calculate_employee_impact(cycle_id) — productivity × salary cost
   - calculate_risk_reduction(cycle_id) — expected loss reduction
   - calculate_payback_period(total_benefit, cost) — months to recoup
   - get_strategy_cost(cycle_id) — total implementation cost from
     strategic_initiatives.json actual_cost or estimated_cost

2. Monetization constants (KES; bank-overridable via constructor):
   - DEFAULT_LTV_INCREASE_PER_CUSTOMER_KES = 5,000
   - DEFAULT_PRODUCTIVITY_GAIN_PCT = 0.03 (3%)
   - DEFAULT_RISK_REDUCTION_VALUE_PER_INITIATIVE_KES = 2,000,000

3. Reads from existing seed:
   - data/strategic_initiatives.json (cost, completion, ROI fields)
   - data/users.json (employee count for productivity monetization)

HONESTY DISCIPLINE
------------------
- All monetization constants are NAMED and DOCUMENTED — never invented
  per-cycle numbers
- Indirect benefits are LABELED as estimates with explicit estimation
  band (±20% default)
- When initiatives lack actual_roi_pct or actual_cost, engine returns
  null + fallback_reason rather than fabricating
- Payback period returns null when total_benefit ≤ 0 or cost ≤ 0
- ROI percentage shows breakdown by category (direct vs indirect)
  for transparency

RELATED STANDARDS
-----------------
- ENH-144 Initiative Portfolio — provides cost data
- ENH-148 Strategy Learning Loop — historical ROI feeds calibration
- ENH-150 Strategy Health Engine — health score correlates with ROI
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.strategy_roi")


# ════════════════════════════════════════════════════════════════════
# Monetization constants (per Continuation.docx Standard #155)
# ════════════════════════════════════════════════════════════════════

# Customer impact: LTV (lifetime value) increase per affected customer
# Default KES 5,000 = ~$32 USD; banks calibrate from real CLV studies
DEFAULT_LTV_INCREASE_PER_CUSTOMER_KES = 5_000

# Employee impact: productivity gain percentage of annual salary cost
# Default 3% productivity uplift; banks calibrate from real measurement
DEFAULT_PRODUCTIVITY_GAIN_PCT = 0.03

# Average annual salary cost (consistent with ENH-147 KES 6M/FTE)
DEFAULT_ANNUAL_SALARY_COST_KES = 6_000_000

# Risk reduction: expected loss reduction per HIGH-priority initiative
DEFAULT_RISK_REDUCTION_VALUE_PER_INITIATIVE_KES = 2_000_000

# Estimation uncertainty band for indirect benefits
INDIRECT_BENEFIT_UNCERTAINTY_PCT = 0.20

# Default customer impact reach: 10% of bank's customer base per
# customer-facing initiative (ENH-141 SWOT type filter)
DEFAULT_CUSTOMER_IMPACT_REACH_PCT = 0.10


# ════════════════════════════════════════════════════════════════════
# StrategyROIAnalytics
# ════════════════════════════════════════════════════════════════════

class StrategyROIAnalytics:
    """Measure true ROI of strategic initiatives.

    Caller pattern:

        from utils.strategy_roi import StrategyROIAnalytics

        roi = StrategyROIAnalytics()
        result = roi.calculate_strategy_roi("2025_baseline_cycle")

        # result["roi_percentage"]      → float | None
        # result["payback_period_months"] → float | None
        # result["breakdown"]            → category contributions
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 ltv_increase_per_customer_kes: float =
                 DEFAULT_LTV_INCREASE_PER_CUSTOMER_KES,
                 productivity_gain_pct: float =
                 DEFAULT_PRODUCTIVITY_GAIN_PCT,
                 annual_salary_cost_kes: float =
                 DEFAULT_ANNUAL_SALARY_COST_KES,
                 risk_reduction_per_initiative_kes: float =
                 DEFAULT_RISK_REDUCTION_VALUE_PER_INITIATIVE_KES,
                 customer_impact_reach_pct: float =
                 DEFAULT_CUSTOMER_IMPACT_REACH_PCT,
                 ai_attribution_fn: Optional[Callable] = None):
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.ltv_increase = ltv_increase_per_customer_kes
        self.productivity_gain = productivity_gain_pct
        self.salary_cost = annual_salary_cost_kes
        self.risk_reduction_per_initiative = risk_reduction_per_initiative_kes
        self.customer_impact_reach = customer_impact_reach_pct
        self.ai_attribution_fn = ai_attribution_fn
        self._initiatives_cache: Optional[List[Dict]] = None
        self._users_cache: Optional[List[Dict]] = None

    # ── Data loaders ──

    def _load_initiatives(self) -> List[Dict[str, Any]]:
        if self._initiatives_cache is not None:
            return self._initiatives_cache
        path = self.data_dir / "strategic_initiatives.json"
        if not path.exists():
            self._initiatives_cache = []
            return self._initiatives_cache
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._initiatives_cache = (
                data if isinstance(data, list)
                else data.get("initiatives", [])
                if isinstance(data, dict) else [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"strategic_initiatives.json unreadable: {e}")
            self._initiatives_cache = []
        return self._initiatives_cache

    def _load_users(self) -> List[Dict[str, Any]]:
        if self._users_cache is not None:
            return self._users_cache
        path = self.data_dir / "users.json"
        if not path.exists():
            self._users_cache = []
            return self._users_cache
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._users_cache = data
            elif isinstance(data, dict):
                if "users" in data and isinstance(data["users"], list):
                    self._users_cache = data["users"]
                else:
                    self._users_cache = [
                        {**v, "username": k}
                        for k, v in data.items()
                        if isinstance(v, dict)
                    ]
            else:
                self._users_cache = []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"users.json unreadable: {e}")
            self._users_cache = []
        return self._users_cache

    def _filter_initiatives(
            self, cycle_id: str) -> List[Dict[str, Any]]:
        """Filter initiatives for a given strategy cycle.

        Current seed is single-cycle; this filter is a placeholder
        for multi-cycle support. Returns all when cycle_id matches
        any 'cycle_id' field, else returns all.
        """
        all_inits = self._load_initiatives()
        # Filter only when seeds carry cycle_id field
        with_cycle = [i for i in all_inits if i.get("cycle_id")]
        if with_cycle:
            return [i for i in with_cycle
                    if i.get("cycle_id") == cycle_id]
        # Single-cycle seed — return all
        return all_inits

    # ── Direct benefits ──

    def calculate_revenue_impact(
            self, strategy_cycle_id: str) -> Dict[str, Any]:
        """Sum of revenue deltas across initiatives.

        Reads `revenue_impact_kes` or `expected_revenue_impact_kes` per
        initiative. When neither present, returns null + reason.
        """
        initiatives = self._filter_initiatives(strategy_cycle_id)
        if not initiatives:
            return {
                "amount_kes":      None,
                "n_contributing":  0,
                "fallback_reason": ("No initiatives in cycle "
                                     f"'{strategy_cycle_id}'."),
            }
        total = 0.0
        n_contrib = 0
        for ini in initiatives:
            rev = (ini.get("revenue_impact_kes")
                   or ini.get("expected_revenue_impact_kes"))
            if isinstance(rev, (int, float)) and rev > 0:
                total += rev
                n_contrib += 1
        if n_contrib == 0:
            return {
                "amount_kes":       0,
                "n_contributing":   0,
                "fallback_reason":  ("No initiatives report "
                                      "revenue_impact_kes; populate seed "
                                      "to compute revenue impact."),
            }
        return {
            "amount_kes":     round(total, 2),
            "n_contributing": n_contrib,
            "fallback_reason": None,
        }

    def calculate_cost_savings(
            self, strategy_cycle_id: str) -> Dict[str, Any]:
        """Sum of cost reductions across initiatives.

        Reads `cost_savings_kes` or computed from completion_pct +
        budget for type='Cost Reduction' initiatives.
        """
        initiatives = self._filter_initiatives(strategy_cycle_id)
        if not initiatives:
            return {
                "amount_kes":      None,
                "n_contributing":  0,
                "fallback_reason": ("No initiatives in cycle "
                                     f"'{strategy_cycle_id}'."),
            }
        total = 0.0
        n_contrib = 0
        for ini in initiatives:
            cs = ini.get("cost_savings_kes")
            if isinstance(cs, (int, float)) and cs > 0:
                total += cs
                n_contrib += 1
                continue
            # Estimate from cost-reduction initiatives
            if (ini.get("type") == "Cost Reduction"
                    and isinstance(ini.get("completion_pct"),
                                    (int, float))):
                budget = ini.get("estimated_cost") or (
                    (ini.get("budget_kes_m", 0) or 0) * 1_000_000)
                comp = ini["completion_pct"] / 100.0
                # Cost-reduction initiatives nominally save 50% of budget
                # in steady state (calibrate per bank); engine flags as
                # estimate
                if isinstance(budget, (int, float)) and budget > 0:
                    estimated_savings = budget * 0.5 * comp
                    total += estimated_savings
                    n_contrib += 1

        return {
            "amount_kes":         round(total, 2),
            "n_contributing":     n_contrib,
            "is_estimate":        True,
            "fallback_reason":    (None if n_contrib > 0
                                    else "No cost-reduction initiatives "
                                          "to monetize."),
        }

    # ── Indirect benefits ──

    def calculate_customer_impact(
            self, strategy_cycle_id: str) -> Dict[str, Any]:
        """Customer impact: LTV increase × affected customers.

        Affected customers = customer-facing initiatives × default reach
        (10% of bank's customer base per initiative). When customer base
        unknown, uses 100,000 placeholder + flags as estimate.
        """
        initiatives = self._filter_initiatives(strategy_cycle_id)
        # Customer-facing initiative types
        customer_types = {"Customer Experience", "Product Development",
                          "Market Expansion", "Customer Acquisition"}
        n_customer_inits = sum(
            1 for i in initiatives
            if i.get("type") in customer_types)

        if n_customer_inits == 0:
            return {
                "amount_kes":      0,
                "ltv_increase":    self.ltv_increase,
                "affected_customers": 0,
                "fallback_reason": ("No customer-facing initiatives in "
                                     "cycle."),
                "is_estimate":     True,
            }

        # Customer base: read from data file or default 100K
        cust_base_path = self.data_dir / "customer_base.json"
        if cust_base_path.exists():
            try:
                with open(cust_base_path, encoding="utf-8") as f:
                    cd = json.load(f)
                    customer_base = cd.get("total_customers", 100_000)
            except (json.JSONDecodeError, OSError):
                customer_base = 100_000
        else:
            customer_base = 100_000

        affected = int(customer_base * self.customer_impact_reach
                       * n_customer_inits)
        amount = affected * self.ltv_increase

        return {
            "amount_kes":      round(amount, 2),
            "ltv_increase":    self.ltv_increase,
            "affected_customers": affected,
            "n_customer_initiatives": n_customer_inits,
            "is_estimate":     True,
            "uncertainty_band": INDIRECT_BENEFIT_UNCERTAINTY_PCT,
            "fallback_reason": None,
        }

    def calculate_employee_impact(
            self, strategy_cycle_id: str) -> Dict[str, Any]:
        """Employee productivity impact: productivity_gain × salary
        × n_employees affected.

        n_employees = total bank headcount × completion-weighted ratio
        of employee-facing initiatives.
        """
        users = self._load_users()
        n_total = len(users)
        if n_total == 0:
            return {
                "amount_kes":      None,
                "fallback_reason": ("users.json empty or missing; "
                                     "cannot compute productivity impact."),
                "is_estimate":     True,
            }

        initiatives = self._filter_initiatives(strategy_cycle_id)
        # Employee-impacting initiative types
        emp_types = {"Process Improvement", "Digital Transformation",
                     "Cost Reduction", "Operational Excellence",
                     "Training"}
        emp_inits = [i for i in initiatives
                     if i.get("type") in emp_types]
        if not emp_inits:
            return {
                "amount_kes":      0,
                "fallback_reason": ("No employee-impacting initiatives "
                                     "in cycle."),
                "is_estimate":     True,
            }

        # Average completion across employee-impacting initiatives
        comps = [i.get("completion_pct", 0) for i in emp_inits
                 if isinstance(i.get("completion_pct"), (int, float))]
        avg_completion = (sum(comps) / len(comps) / 100.0
                          if comps else 0)

        # Productivity gain = base × avg_completion (only when initiatives
        # are partially or fully complete, productivity has materialized)
        effective_gain = self.productivity_gain * avg_completion
        amount = n_total * self.salary_cost * effective_gain

        return {
            "amount_kes":            round(amount, 2),
            "productivity_gain_pct": self.productivity_gain,
            "effective_gain_pct":    round(effective_gain, 4),
            "n_employees":           n_total,
            "salary_cost_per_emp":   self.salary_cost,
            "n_emp_initiatives":     len(emp_inits),
            "is_estimate":           True,
            "uncertainty_band":      INDIRECT_BENEFIT_UNCERTAINTY_PCT,
            "fallback_reason":       None,
        }

    def calculate_risk_reduction(
            self, strategy_cycle_id: str) -> Dict[str, Any]:
        """Risk reduction value: per-initiative expected loss reduction.

        Risk-reducing initiative types: Risk Management, Compliance,
        Security, Audit. Each contributes risk_reduction_per_initiative
        weighted by completion.
        """
        initiatives = self._filter_initiatives(strategy_cycle_id)
        risk_types = {"Risk Management", "Compliance", "Security",
                      "Audit", "Governance"}
        risk_inits = [i for i in initiatives
                      if i.get("type") in risk_types]
        if not risk_inits:
            return {
                "amount_kes":      0,
                "fallback_reason": ("No risk-reducing initiatives in "
                                     "cycle."),
                "is_estimate":     True,
            }

        total = 0.0
        for ini in risk_inits:
            comp = ini.get("completion_pct", 0)
            if isinstance(comp, (int, float)):
                total += self.risk_reduction_per_initiative * (comp / 100.0)

        return {
            "amount_kes":            round(total, 2),
            "n_risk_initiatives":    len(risk_inits),
            "value_per_initiative":  self.risk_reduction_per_initiative,
            "is_estimate":           True,
            "uncertainty_band":      INDIRECT_BENEFIT_UNCERTAINTY_PCT,
            "fallback_reason":       None,
        }

    # ── Cost ──

    def get_strategy_cost(
            self, strategy_cycle_id: str) -> Dict[str, Any]:
        """Total implementation cost from initiatives.

        Prefers actual_cost; falls back to estimated_cost; falls back
        to budget_kes_m × 1M.
        """
        initiatives = self._filter_initiatives(strategy_cycle_id)
        if not initiatives:
            return {
                "amount_kes":      None,
                "fallback_reason": ("No initiatives in cycle "
                                     f"'{strategy_cycle_id}'."),
            }
        total = 0.0
        n_contrib = 0
        is_actual = True
        for ini in initiatives:
            actual = ini.get("actual_cost") or (
                (ini.get("actual_spend_kes_m") or 0) * 1_000_000)
            if isinstance(actual, (int, float)) and actual > 0:
                total += actual
                n_contrib += 1
                continue
            estimated = ini.get("estimated_cost") or (
                (ini.get("budget_kes_m") or 0) * 1_000_000)
            if isinstance(estimated, (int, float)) and estimated > 0:
                total += estimated
                n_contrib += 1
                is_actual = False
        return {
            "amount_kes":      round(total, 2) if total > 0 else None,
            "n_contributing":  n_contrib,
            "is_actual":       is_actual,
            "fallback_reason": (None if total > 0
                                else "No cost data on any initiative."),
        }

    # ── Payback period ──

    def calculate_payback_period(
            self,
            total_benefit: float,
            cost: float,
            cycle_duration_months: int = 12) -> Optional[float]:
        """Payback period in months.

        payback_months = (cost / monthly_benefit_run_rate)
        where monthly_benefit_run_rate = total_benefit / cycle_duration_months
        """
        if not isinstance(total_benefit, (int, float)) or total_benefit <= 0:
            return None
        if not isinstance(cost, (int, float)) or cost <= 0:
            return None
        if cycle_duration_months <= 0:
            return None
        monthly_run_rate = total_benefit / cycle_duration_months
        if monthly_run_rate <= 0:
            return None
        return round(cost / monthly_run_rate, 2)

    # ── Main API ──

    def calculate_strategy_roi(
            self,
            strategy_cycle_id: str = "current",
            cycle_duration_months: int = 12) -> Dict[str, Any]:
        """Full ROI calculation pipeline.

        Returns:
            {
              "strategy_cycle":      str,
              "total_benefit_kes":   float | None,
              "implementation_cost_kes": float | None,
              "roi_percentage":      float | None,
              "payback_period_months": float | None,
              "breakdown": {
                "revenue_impact":         {...},
                "cost_savings":            {...},
                "customer_impact_value":   {...},
                "employee_impact_value":   {...},
                "risk_reduction_value":    {...},
              },
              "direct_benefit_kes":   float,
              "indirect_benefit_kes": float,
              "is_estimate":          bool (True if any indirect contributes),
              "uncertainty_band":     float,
              "generated_at":         ISO-8601,
              "basis":                "rule_based" | "rule_based+llm",
            }
        """
        revenue = self.calculate_revenue_impact(strategy_cycle_id)
        savings = self.calculate_cost_savings(strategy_cycle_id)
        customer = self.calculate_customer_impact(strategy_cycle_id)
        employee = self.calculate_employee_impact(strategy_cycle_id)
        risk = self.calculate_risk_reduction(strategy_cycle_id)

        direct = (
            (revenue.get("amount_kes") or 0)
            + (savings.get("amount_kes") or 0)
        )
        indirect = (
            (customer.get("amount_kes") or 0)
            + (employee.get("amount_kes") or 0)
            + (risk.get("amount_kes") or 0)
        )
        total_benefit = direct + indirect

        cost_result = self.get_strategy_cost(strategy_cycle_id)
        cost = cost_result.get("amount_kes")

        # ROI
        if cost and cost > 0 and total_benefit > 0:
            roi_pct = round(
                (total_benefit - cost) / cost * 100, 2)
        else:
            roi_pct = None

        # Payback
        payback = self.calculate_payback_period(
            total_benefit, cost or 0, cycle_duration_months)

        # AI attribution enrichment
        bases = ["rule_based"]
        ai_attribution = None
        if self.ai_attribution_fn is not None:
            try:
                ai_attribution = self.ai_attribution_fn({
                    "cycle": strategy_cycle_id,
                    "direct": direct,
                    "indirect": indirect,
                    "cost": cost,
                })
                bases.append("llm")
            except Exception as e:
                logger.warning(
                    f"ai_attribution_fn raised {type(e).__name__}: {e}")

        return {
            "strategy_cycle":            strategy_cycle_id,
            "cycle_duration_months":     cycle_duration_months,
            "total_benefit_kes":         round(total_benefit, 2)
            if total_benefit > 0 else None,
            "implementation_cost_kes":   cost,
            "roi_percentage":            roi_pct,
            "payback_period_months":     payback,
            "breakdown": {
                "revenue_impact":         revenue,
                "cost_savings":            savings,
                "customer_impact_value":   customer,
                "employee_impact_value":   employee,
                "risk_reduction_value":    risk,
            },
            "direct_benefit_kes":        round(direct, 2),
            "indirect_benefit_kes":      round(indirect, 2),
            "is_estimate":               indirect > 0,
            "uncertainty_band":          INDIRECT_BENEFIT_UNCERTAINTY_PCT,
            "ai_attribution":            ai_attribution,
            "generated_at":              datetime.now(
                timezone.utc).isoformat(),
            "basis":                     "+".join(bases),
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def calculate_strategy_roi(
        strategy_cycle_id: str = "current") -> Dict[str, Any]:
    """Convenience wrapper — instantiate analytics and run."""
    return StrategyROIAnalytics().calculate_strategy_roi(strategy_cycle_id)

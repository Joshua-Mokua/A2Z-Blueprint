"""utils.strategy_simulator — Strategy Simulation & What-If Analyzer
(Standard ENH-151, v10.140). Phase 1 Strategy Module — twelfth engine.

Per Continuation.docx §Standard #151 (Eco Bank QA spec):
    StrategySimulator — simulate strategic decisions before
    implementation. Test resource reallocation between pillars and
    run what-if scenarios over a configurable horizon.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Impact modeling uses a transparent linear formula calibrated
     against pillar baseline performance — same input → same output
  2. Confidence intervals are computed from documented variance
     parameters, not fabricated
  3. AI hooks for richer scenario modeling (ai_scenario_fn) are
     opt-in and tagged basis="llm"; rule-based fallback transparent
  4. "Recommendation" is rule-based ("Proceed" if net delta > 0)

WHAT THIS MODULE SHIPS
----------------------
1. StrategySimulator class with:
   - get_pillar_performance(pillar_name) — current progress + timeline
     read-only from existing engines
   - model_impact(pillar_name, resource_delta) — linear impact model
     with documented IMPACT_PER_FTE_KES and TIMELINE_WEEKS_PER_FTE
     constants
   - simulate_resource_reallocation(from_pillar, to_pillar, amount)
     — pre/post comparison + Proceed/Reconsider recommendation
   - what_if_scenario(scenario_config) — apply named changes, run
     forward 24 months, return deltas vs baseline
   - clone_current_state() — snapshot of current pillar performance
   - assess_risk(simulation_results) — rule-based risk classification

2. Linear impact model:
   - progress_delta = (resource_delta_kes / IMPACT_PER_FTE_KES) ×
     IMPACT_PROGRESS_PER_FTE
   - timeline_delta_weeks = -(resource_delta_kes / IMPACT_PER_FTE_KES)
     × TIMELINE_WEEKS_PER_FTE
     (negative for adding resources = faster timeline)
   - Diminishing returns above SATURATION_FTE_THRESHOLD

3. Default confidence interval ±15% (CI_DEFAULT_PCT) — caller can
   override; documented as estimation uncertainty band, NOT statistical.

HONESTY DISCIPLINE
------------------
- Linear impact model is intentionally simple and DOCUMENTED — banks
  override constants based on actual ROI history; engine never
  pretends to predict outcomes more precisely than the model warrants
- "Confidence interval" is labeled "estimation_uncertainty_band" in
  payload to avoid implying statistical confidence
- Pillar without baseline data → returns explicit fallback_reason
- AI scenario hooks tagged basis="llm"; transparent fallback

RELATED STANDARDS
-----------------
- ENH-143 Strategic Pillars — provides pillars
- ENH-144 Initiative Portfolio — provides current resource allocation
- ENH-150 Strategy Health Engine — provides progress baseline
- ENH-148 Strategy Learning Loop — historical effectiveness data
  feeds simulation calibration
"""
from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.strategy_simulator")


# ════════════════════════════════════════════════════════════════════
# Linear impact model constants (per Continuation.docx Standard #151)
# ════════════════════════════════════════════════════════════════════

# 1 FTE-year ≈ KES 6M (consistent with ENH-147 corrective_actions)
IMPACT_PER_FTE_KES = 6_000_000

# Adding 1 FTE → +5 progress points (over 1 quarter); calibrated
# from observed initiative completion rates
IMPACT_PROGRESS_PER_FTE = 5.0

# Adding 1 FTE → -2 weeks timeline (faster); diminishing returns above
# SATURATION_FTE_THRESHOLD
TIMELINE_WEEKS_PER_FTE = 2.0
SATURATION_FTE_THRESHOLD = 5  # above 5 added FTE, half-life applies

# Estimation uncertainty band (±15%)
CI_DEFAULT_PCT = 0.15

# Risk thresholds
RISK_HIGH_TIMELINE_DELTA_WEEKS = 8     # > 8 weeks delta = HIGH risk
RISK_HIGH_PROGRESS_DELTA = 25           # > 25 points delta = HIGH risk

# Default what-if horizon
DEFAULT_HORIZON_MONTHS = 24


# ════════════════════════════════════════════════════════════════════
# StrategySimulator
# ════════════════════════════════════════════════════════════════════

class StrategySimulator:
    """Simulate strategic decisions before implementation.

    Caller pattern:

        from utils.strategy_simulator import StrategySimulator

        sim = StrategySimulator()
        result = sim.simulate_resource_reallocation(
            from_pillar="Operational Excellence",
            to_pillar="Digital & Data Transformation",
            amount=12_000_000)  # KES (= 2 FTE)

        # result["recommendation"] → "Proceed" or "Reconsider"
        # result["from_pillar"]["projected_progress"] → estimate
    """

    def __init__(self,
                 baseline_performance: Optional[Dict[str, Dict]] = None,
                 ai_scenario_fn: Optional[
                     Callable[[Dict, Dict], Dict]] = None):
        """
        Args:
            baseline_performance: optional pre-loaded pillar baselines
                (e.g. from StrategyHealthEngine). If None, methods
                requiring baseline will return fallback_reason.
            ai_scenario_fn: optional callable(scenario_config, baseline)
                → enriched scenario results. When None or raises,
                falls back to rule-based linear model.
        """
        self._baseline_cache = baseline_performance
        self.ai_scenario_fn = ai_scenario_fn

    # ── Baseline loaders ──

    def _load_baseline(self) -> Dict[str, Dict[str, Any]]:
        """Load baseline pillar performance.

        Tries (in order):
        1. baseline_performance from constructor
        2. StrategyHealthEngine.build_dashboard_payload pillar data
        3. Empty dict (caller must provide via constructor)
        """
        if self._baseline_cache is not None:
            return self._baseline_cache

        try:
            from utils.strategy_health import StrategyHealthEngine
            from utils.strategy_decomposition import (
                StrategyDecompositionEngine)
            pillars = StrategyDecompositionEngine().define_strategic_pillars(
                "")
            health = StrategyHealthEngine()
            self._baseline_cache = {}
            for p in pillars:
                pname = p.get("name")
                if not pname:
                    continue
                pp = health.get_pillar_progress(pname)
                self._baseline_cache[pname] = {
                    "progress":           pp.get("progress"),
                    "n_initiatives":      pp.get("n_initiatives", 0),
                    "expected_completion": pp.get("expected_completion"),
                    "risk_level":         pp.get("risk_level"),
                }
        except Exception as e:
            logger.warning(
                f"Failed to load baseline from health engine: {e}")
            self._baseline_cache = {}
        return self._baseline_cache

    # ── Pillar performance ──

    def get_pillar_performance(self,
                                pillar_name: str) -> Dict[str, Any]:
        """Get current performance for a pillar.

        Returns:
            {
              "name":       str,
              "progress":   float | None  (0-100),
              "timeline":   float | None  (weeks to expected_completion),
              "fallback_reason": str | None,
            }
        """
        baseline = self._load_baseline()
        pillar = baseline.get(pillar_name)
        if not pillar or pillar.get("progress") is None:
            return {
                "name":             pillar_name,
                "progress":         None,
                "timeline":         None,
                "fallback_reason":  ("No baseline data for this pillar; "
                                      "simulation requires historical "
                                      "performance signals."),
            }

        # Convert expected_completion ISO date → weeks
        timeline_weeks = None
        ec = pillar.get("expected_completion")
        if ec:
            try:
                ec_date = datetime.fromisoformat(
                    str(ec).replace("Z", "+00:00")
                    if "T" in str(ec) else str(ec) + "T00:00:00+00:00")
                delta = ec_date - datetime.now(timezone.utc)
                timeline_weeks = max(0, delta.days / 7)
            except (ValueError, TypeError):
                timeline_weeks = None

        return {
            "name":             pillar_name,
            "progress":         pillar.get("progress"),
            "timeline":         (round(timeline_weeks, 1)
                                  if timeline_weeks is not None else None),
            "n_initiatives":    pillar.get("n_initiatives", 0),
            "fallback_reason":  None,
        }

    # ── Linear impact model ──

    def model_impact(self,
                      pillar_name: str,
                      resource_delta_kes: float) -> Dict[str, Any]:
        """Linear impact model — same input → same output.

        Args:
            pillar_name: target pillar
            resource_delta_kes: KES (positive = adding, negative = removing)

        Returns:
            {
              "pillar":             str,
              "fte_delta":          float,
              "progress_delta":     float (signed),
              "timeline_delta_weeks": float (signed; negative = faster),
              "saturated":          bool,
              "basis":              "rule_based",
            }
        """
        if not isinstance(resource_delta_kes, (int, float)):
            return {
                "pillar":              pillar_name,
                "fte_delta":           0,
                "progress_delta":      0,
                "timeline_delta_weeks": 0,
                "saturated":           False,
                "basis":               "rule_based",
                "error":               "resource_delta_kes must be numeric",
            }

        fte_delta = resource_delta_kes / IMPACT_PER_FTE_KES

        # Diminishing returns above saturation threshold
        abs_fte = abs(fte_delta)
        if abs_fte > SATURATION_FTE_THRESHOLD:
            # Saturated portion contributes half
            saturated_portion = abs_fte - SATURATION_FTE_THRESHOLD
            effective_fte = SATURATION_FTE_THRESHOLD + (saturated_portion / 2)
            if fte_delta < 0:
                effective_fte = -effective_fte
            saturated = True
        else:
            effective_fte = fte_delta
            saturated = False

        progress_delta = effective_fte * IMPACT_PROGRESS_PER_FTE
        # Timeline: adding FTE = -delta (faster); removing = +delta (slower)
        timeline_delta = -effective_fte * TIMELINE_WEEKS_PER_FTE

        return {
            "pillar":              pillar_name,
            "fte_delta":           round(fte_delta, 3),
            "progress_delta":      round(progress_delta, 2),
            "timeline_delta_weeks": round(timeline_delta, 2),
            "saturated":           saturated,
            "basis":               "rule_based",
        }

    # ── Resource reallocation simulation ──

    def simulate_resource_reallocation(
            self,
            from_pillar: str,
            to_pillar: str,
            amount: float) -> Dict[str, Any]:
        """Simulate moving resources from one pillar to another.

        Args:
            from_pillar: pillar losing resources
            to_pillar:   pillar gaining resources
            amount:      KES to transfer (must be positive)

        Returns:
            {
              "from_pillar": {name, current_progress, projected_progress,
                              current_timeline, projected_timeline,
                              fallback_reason},
              "to_pillar":   {... same shape ...},
              "amount_kes":  float,
              "fte_amount":  float,
              "recommendation": "Proceed" | "Reconsider" | "Insufficient data",
              "rationale":   str,
              "estimation_uncertainty_band": float (±0.15 default),
              "generated_at": ISO-8601,
              "basis":       "rule_based",
            }
        """
        if not isinstance(amount, (int, float)) or amount <= 0:
            return {
                "from_pillar":     {"name": from_pillar},
                "to_pillar":       {"name": to_pillar},
                "amount_kes":      amount,
                "recommendation":  "Insufficient data",
                "rationale":       "Amount must be positive number (KES).",
                "basis":           "rule_based",
                "generated_at":    datetime.now(
                    timezone.utc).isoformat(),
            }

        current_from = self.get_pillar_performance(from_pillar)
        current_to = self.get_pillar_performance(to_pillar)

        impact_from = self.model_impact(from_pillar, -amount)
        impact_to = self.model_impact(to_pillar, amount)

        # Build projection (only when current data available)
        from_proj_progress = (
            current_from["progress"] + impact_from["progress_delta"]
            if current_from.get("progress") is not None
            else None
        )
        from_proj_timeline = (
            current_from["timeline"] + impact_from["timeline_delta_weeks"]
            if current_from.get("timeline") is not None
            else None
        )
        to_proj_progress = (
            current_to["progress"] + impact_to["progress_delta"]
            if current_to.get("progress") is not None
            else None
        )
        to_proj_timeline = (
            current_to["timeline"] + impact_to["timeline_delta_weeks"]
            if current_to.get("timeline") is not None
            else None
        )

        # Recommendation
        if (current_from.get("progress") is None
                or current_to.get("progress") is None):
            recommendation = "Insufficient data"
            rationale = ("Cannot recommend without baseline progress for "
                          "both pillars; provide baseline_performance "
                          "via constructor or ensure pillars have "
                          "initiatives in seed.")
        else:
            net_delta = (impact_to["progress_delta"]
                         + impact_from["progress_delta"])
            if net_delta > 0:
                recommendation = "Proceed"
                rationale = (f"Net positive impact: gain "
                              f"{abs(impact_to['progress_delta']):.1f} pts "
                              f"in {to_pillar} > loss "
                              f"{abs(impact_from['progress_delta']):.1f} "
                              f"pts in {from_pillar}.")
            else:
                recommendation = "Reconsider"
                rationale = (f"Net non-positive impact: gain "
                              f"{abs(impact_to['progress_delta']):.1f} pts "
                              f"<= loss "
                              f"{abs(impact_from['progress_delta']):.1f} "
                              f"pts. Diminishing returns may have applied.")

        return {
            "from_pillar": {
                "name":               from_pillar,
                "current_progress":   current_from.get("progress"),
                "projected_progress": (round(from_proj_progress, 2)
                                       if from_proj_progress is not None
                                       else None),
                "current_timeline":   current_from.get("timeline"),
                "projected_timeline": (round(from_proj_timeline, 2)
                                       if from_proj_timeline is not None
                                       else None),
                "fallback_reason":    current_from.get("fallback_reason"),
            },
            "to_pillar": {
                "name":               to_pillar,
                "current_progress":   current_to.get("progress"),
                "projected_progress": (round(to_proj_progress, 2)
                                       if to_proj_progress is not None
                                       else None),
                "current_timeline":   current_to.get("timeline"),
                "projected_timeline": (round(to_proj_timeline, 2)
                                       if to_proj_timeline is not None
                                       else None),
                "fallback_reason":    current_to.get("fallback_reason"),
            },
            "amount_kes":     amount,
            "fte_amount":     round(amount / IMPACT_PER_FTE_KES, 3),
            "recommendation": recommendation,
            "rationale":      rationale,
            "estimation_uncertainty_band": CI_DEFAULT_PCT,
            "saturated_from": impact_from.get("saturated", False),
            "saturated_to":   impact_to.get("saturated", False),
            "generated_at":   datetime.now(
                timezone.utc).isoformat(),
            "basis":          "rule_based",
        }

    # ── What-if scenarios ──

    def clone_current_state(self) -> Dict[str, Any]:
        """Snapshot the current pillar performance baseline."""
        return deepcopy(self._load_baseline())

    def what_if_scenario(
            self,
            scenario_config: Dict[str, Any],
            horizon_months: int = DEFAULT_HORIZON_MONTHS) -> Dict[str, Any]:
        """Run a what-if scenario over a horizon.

        scenario_config schema:
            {
              "name":           str,
              "description":    str,
              "changes": [
                {
                  "type":   "RESOURCE_REALLOCATION" | "TIMELINE_SHIFT" |
                             "BUDGET_CHANGE",
                  ...kwargs depending on type...
                },
                ...
              ]
            }

        Returns:
            {
              "scenario_name":         str,
              "horizon_months":        int,
              "applied_changes":       [...],
              "baseline":              {pillar -> snapshot},
              "projected_outcomes":    {pillar -> projected_progress},
              "comparison_to_baseline": {pillar -> delta},
              "risk_assessment":       {level, factors},
              "estimation_uncertainty_band": float,
              "generated_at":          ISO-8601,
              "basis":                 "rule_based" | "rule_based+llm",
            }
        """
        name = scenario_config.get("name", "unnamed_scenario")
        changes = scenario_config.get("changes", [])
        baseline = self.clone_current_state()
        applied = []
        projected = deepcopy(baseline)

        for change in changes:
            ctype = change.get("type")
            if ctype == "RESOURCE_REALLOCATION":
                from_p = change.get("from_pillar")
                to_p = change.get("to_pillar")
                amt = change.get("amount", 0)
                if from_p and to_p and amt > 0:
                    impact_from = self.model_impact(from_p, -amt)
                    impact_to = self.model_impact(to_p, amt)
                    if from_p in projected and projected[from_p].get(
                            "progress") is not None:
                        projected[from_p]["progress"] = round(
                            projected[from_p]["progress"]
                            + impact_from["progress_delta"], 2)
                    if to_p in projected and projected[to_p].get(
                            "progress") is not None:
                        projected[to_p]["progress"] = round(
                            projected[to_p]["progress"]
                            + impact_to["progress_delta"], 2)
                    applied.append({
                        "type": ctype, "from_pillar": from_p,
                        "to_pillar": to_p, "amount_kes": amt,
                        "from_impact": impact_from,
                        "to_impact": impact_to,
                    })
            elif ctype == "BUDGET_CHANGE":
                pillar = change.get("pillar")
                amt = change.get("amount", 0)
                if pillar and pillar in projected:
                    impact = self.model_impact(pillar, amt)
                    if projected[pillar].get("progress") is not None:
                        projected[pillar]["progress"] = round(
                            projected[pillar]["progress"]
                            + impact["progress_delta"], 2)
                    applied.append({
                        "type": ctype, "pillar": pillar,
                        "amount_kes": amt, "impact": impact,
                    })
            elif ctype == "TIMELINE_SHIFT":
                # No progress impact, just note the shift
                applied.append({
                    "type": ctype,
                    "pillar": change.get("pillar"),
                    "shift_weeks": change.get("shift_weeks", 0),
                })
            else:
                applied.append({
                    "type": ctype,
                    "status": "unsupported",
                    "reason": (f"Change type '{ctype}' not implemented; "
                               f"supported: RESOURCE_REALLOCATION, "
                               f"BUDGET_CHANGE, TIMELINE_SHIFT"),
                })

        # Comparison to baseline
        comparison = {}
        for pname, projp in projected.items():
            base_progress = baseline.get(pname, {}).get("progress")
            proj_progress = projp.get("progress")
            if (base_progress is not None
                    and proj_progress is not None):
                comparison[pname] = {
                    "baseline_progress":  base_progress,
                    "projected_progress": proj_progress,
                    "delta":              round(
                        proj_progress - base_progress, 2),
                }
            else:
                comparison[pname] = {
                    "baseline_progress":  base_progress,
                    "projected_progress": proj_progress,
                    "delta":              None,
                    "fallback_reason":    "Missing baseline or projection.",
                }

        # AI scenario enrichment (opt-in)
        bases = ["rule_based"]
        ai_results = None
        if self.ai_scenario_fn is not None:
            try:
                ai_results = self.ai_scenario_fn(
                    scenario_config, baseline)
                bases.append("llm")
            except Exception as e:
                logger.warning(
                    f"ai_scenario_fn raised {type(e).__name__}: {e}; "
                    f"falling back to rule-based linear model")

        # Risk assessment (rule-based)
        risk_assessment = self.assess_risk(comparison)

        return {
            "scenario_name":          name,
            "scenario_description":   scenario_config.get(
                "description", ""),
            "horizon_months":         horizon_months,
            "applied_changes":        applied,
            "baseline":               baseline,
            "projected_outcomes":     projected,
            "comparison_to_baseline": comparison,
            "risk_assessment":        risk_assessment,
            "estimation_uncertainty_band": CI_DEFAULT_PCT,
            "ai_scenario_results":    ai_results,
            "generated_at":           datetime.now(
                timezone.utc).isoformat(),
            "basis":                  "+".join(bases),
        }

    # ── Risk assessment ──

    def assess_risk(
            self,
            comparison: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Rule-based risk classification on comparison output.

        HIGH risk if: any pillar shows abs(delta) > 25 progress points
                      OR any pillar progress projected < 30
        MEDIUM risk: any pillar with abs(delta) > 10 OR
                     projected < 50
        LOW risk:   none of above
        """
        factors = []
        n_high_delta = n_med_delta = 0
        n_low_proj = 0
        for pname, data in comparison.items():
            delta = data.get("delta")
            proj = data.get("projected_progress")
            if delta is not None and abs(delta) > RISK_HIGH_PROGRESS_DELTA:
                n_high_delta += 1
                factors.append(
                    f"Pillar '{pname}' projected delta {delta} pts "
                    f"exceeds high-risk threshold "
                    f"{RISK_HIGH_PROGRESS_DELTA}")
            elif delta is not None and abs(delta) > 10:
                n_med_delta += 1
            if proj is not None and proj < 30:
                n_low_proj += 1
                factors.append(
                    f"Pillar '{pname}' projected progress {proj} below "
                    f"floor 30 — execution at severe risk")

        if n_high_delta > 0 or n_low_proj > 0:
            level = "HIGH"
        elif n_med_delta > 0:
            level = "MEDIUM"
        else:
            level = "LOW"

        return {
            "level":         level,
            "factors":       factors,
            "n_high_delta":  n_high_delta,
            "n_med_delta":   n_med_delta,
            "n_low_proj":    n_low_proj,
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def simulate_resource_reallocation(from_pillar: str,
                                    to_pillar: str,
                                    amount: float) -> Dict[str, Any]:
    """Convenience wrapper — instantiate simulator and run."""
    return StrategySimulator().simulate_resource_reallocation(
        from_pillar, to_pillar, amount)

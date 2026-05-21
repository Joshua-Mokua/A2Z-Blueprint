"""utils.corrective_actions — Corrective Action Generator
(Standard ENH-147, v10.138). Phase 1 Strategy Module — eighth engine.

Per Continuation.docx §Standard #147 (Eco Bank QA spec):
    CorrectiveActionGenerator — generate AI-powered corrective action
    plans for strategy execution gaps. For each gap, propose specific
    actions (resource reallocation, process redesign, training) with
    estimated closure time, implementation cost, and expected gap
    reduction. Prioritize by impact-per-cost ratio.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Action templates are deterministic over root cause category
  2. Cost/impact estimates use named constants (transparent bands)
  3. Prioritization is deterministic (impact/cost ratio sort)
  4. AI-suggested additional actions opt-in (ai_suggester_fn);
     falls back to rule-based with explicit basis labelling

WHAT THIS MODULE SHIPS
----------------------
1. CorrectiveActionGenerator class with:
   - generate_corrective_actions(gap) — per-gap action plan
   - generate_actions_for_all_gaps(gaps) — batch wrapper
   - prioritize_actions(actions) — impact/cost ratio sort
   - estimate_combined_impact(actions) — sum of expected gap reductions

2. Three default action templates per Continuation.docx Standard #147:
   - RESOURCE_REALLOCATION (for UNDER_RESOURCED gaps)
   - PROCESS_REDESIGN (for PROCESS_BOTTLENECK gaps)
   - TRAINING (for SKILL_GAP gaps)

3. Cost/impact constants (KES-denominated per bank scale):
   - RESOURCE_COST_PER_FTE_KES = 6,000,000 (annual cost of 1 FTE)
   - PROCESS_REDESIGN_COST_KES = 5,000,000 (per redesign)
   - TRAINING_COST_KES = 2,500,000 (per cohort)

4. Expected gap reduction multipliers (per doc spec):
   - RESOURCE_REALLOCATION: 0.50× gap closure
   - PROCESS_REDESIGN:      0.70× gap closure
   - TRAINING:              0.30× gap closure

HONESTY DISCIPLINE
------------------
- Cost estimates are NAMED CONSTANTS, not fabricated per-gap numbers
- Expected gap reduction is the doc-specified multiplier (rule 0.5/0.7/0.3)
- For UNCLASSIFIED gaps, returns a "MANUAL_REVIEW" placeholder action
  with explicit reason rather than fabricating actions
- AI suggestions (when ai_suggester_fn provided) are tagged with
  basis="llm" — never blended with rule-based ones silently
- Deterministic prioritization: same gap → same action ranking

RELATED STANDARDS
-----------------
- ENH-146 Strategy Execution Gap Analyzer — produces gap input
- ENH-148 Strategy Learning Loop (planned v10.139) — captures
  effectiveness of corrective actions for next strategy cycle
- ENH-150 Strategy Health Dashboard (planned v10.139) — surfaces
  active corrective actions
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.corrective_actions")


# ════════════════════════════════════════════════════════════════════
# Constants (per Continuation.docx Standard #147)
# ════════════════════════════════════════════════════════════════════

# Action types (must match keys used by ENH-146 root cause categories)
ACTION_RESOURCE_REALLOCATION = "RESOURCE_REALLOCATION"
ACTION_PROCESS_REDESIGN = "PROCESS_REDESIGN"
ACTION_TRAINING = "TRAINING"
ACTION_MANUAL_REVIEW = "MANUAL_REVIEW"

# Cost constants (KES, annual basis where applicable; bank-specific
# overrides via constructor)
DEFAULT_RESOURCE_COST_PER_FTE_KES = 6_000_000   # senior banker FTE/year
DEFAULT_PROCESS_REDESIGN_COST_KES = 5_000_000   # redesign engagement
DEFAULT_TRAINING_COST_KES = 2_500_000           # cohort training

# Expected gap reduction multipliers (per doc spec)
GAP_REDUCTION_RESOURCE = 0.50
GAP_REDUCTION_PROCESS = 0.70
GAP_REDUCTION_TRAINING = 0.30

# Closure horizons (per doc spec)
HORIZON_RESOURCE = "2 weeks"
HORIZON_PROCESS = "4 weeks"
HORIZON_TRAINING = "2 weeks"


# ════════════════════════════════════════════════════════════════════
# CorrectiveActionGenerator
# ════════════════════════════════════════════════════════════════════

class CorrectiveActionGenerator:
    """Generate corrective actions for strategy execution gaps.

    Caller pattern:

        from utils.gap_analyzer import StrategyGapAnalyzer
        from utils.corrective_actions import CorrectiveActionGenerator

        analyzer = StrategyGapAnalyzer()
        gap_result = analyzer.analyze_gaps(pillars, current_performance)

        generator = CorrectiveActionGenerator()
        for gap in gap_result["gaps"]:
            action_plan = generator.generate_corrective_actions(gap)
            # action_plan["recommended_actions"] → list of prioritized actions
    """

    def __init__(self,
                 resource_cost_per_fte: float = DEFAULT_RESOURCE_COST_PER_FTE_KES,
                 process_redesign_cost: float = DEFAULT_PROCESS_REDESIGN_COST_KES,
                 training_cost: float = DEFAULT_TRAINING_COST_KES,
                 ai_suggester_fn: Optional[
                     Callable[[Dict], List[Dict]]] = None):
        """
        Args:
            resource_cost_per_fte: KES cost of 1 FTE-year (default 6M)
            process_redesign_cost: KES cost of process redesign (default 5M)
            training_cost: KES cost of training cohort (default 2.5M)
            ai_suggester_fn: optional callable(gap_dict) → list of
                additional action dicts. When None or raises, only
                rule-based template is used.
        """
        self.resource_cost_per_fte = resource_cost_per_fte
        self.process_redesign_cost = process_redesign_cost
        self.training_cost = training_cost
        self.ai_suggester_fn = ai_suggester_fn

    # ── Per-action templates ──

    def _resource_action(self, gap: Dict[str, Any]) -> Dict[str, Any]:
        """RESOURCE_REALLOCATION action template.

        FTE estimate scales with gap_percentage:
        - HIGH severity (gap > 30%): 2 FTE
        - MEDIUM severity (gap 10-30%): 1 FTE
        """
        severity = gap.get("severity", "MEDIUM")
        n_fte = 2 if severity == "HIGH" else 1
        cost = n_fte * self.resource_cost_per_fte
        gap_value = gap.get("gap", 0)
        return {
            "type":                    ACTION_RESOURCE_REALLOCATION,
            "description":             (
                f"Reallocate {n_fte} FTE to {gap.get('pillar')} to "
                f"close {gap.get('metric')} gap"),
            "estimated_closure_time":  HORIZON_RESOURCE,
            "implementation_cost":     cost,
            "expected_gap_reduction":  round(
                gap_value * GAP_REDUCTION_RESOURCE, 4),
            "fte_required":            n_fte,
            "basis":                   "rule_based",
        }

    def _process_action(self, gap: Dict[str, Any]) -> Dict[str, Any]:
        """PROCESS_REDESIGN action template.

        TAT reduction target derived from root_cause detail when
        available, else default to 25%.
        """
        root_cause = gap.get("root_cause", {})
        signals = root_cause.get("signals_seen", {})
        tat = signals.get("process_tat")
        target_tat = signals.get("process_target_tat")
        if (isinstance(tat, (int, float)) and isinstance(target_tat, (int, float))
                and target_tat > 0):
            tat_reduction_pct = round(
                (tat / target_tat - 1) * 100, 1)
        else:
            tat_reduction_pct = 25.0

        process_label = (gap.get("metric") or "key process")
        gap_value = gap.get("gap", 0)
        return {
            "type":                    ACTION_PROCESS_REDESIGN,
            "description":             (
                f"Redesign {process_label} process to reduce TAT by "
                f"{tat_reduction_pct}%"),
            "estimated_closure_time":  HORIZON_PROCESS,
            "implementation_cost":     self.process_redesign_cost,
            "expected_gap_reduction":  round(
                gap_value * GAP_REDUCTION_PROCESS, 4),
            "tat_reduction_pct":       tat_reduction_pct,
            "basis":                   "rule_based",
        }

    def _training_action(self, gap: Dict[str, Any]) -> Dict[str, Any]:
        """TRAINING action template."""
        skill_label = gap.get("metric") or "required skill"
        gap_value = gap.get("gap", 0)
        return {
            "type":                    ACTION_TRAINING,
            "description":             (
                f"Conduct {skill_label} training cohort for "
                f"{gap.get('pillar')} team"),
            "estimated_closure_time":  HORIZON_TRAINING,
            "implementation_cost":     self.training_cost,
            "expected_gap_reduction":  round(
                gap_value * GAP_REDUCTION_TRAINING, 4),
            "basis":                   "rule_based",
        }

    def _manual_review_action(self,
                               gap: Dict[str, Any]) -> Dict[str, Any]:
        """Placeholder for UNCLASSIFIED gaps — caller must classify."""
        return {
            "type":                    ACTION_MANUAL_REVIEW,
            "description":             (
                "Root cause unclassified. Manual classification "
                "required: collect resource utilization, process TAT, "
                "and skill gap signals, then re-run gap analyzer."),
            "estimated_closure_time":  "n/a",
            "implementation_cost":     0,
            "expected_gap_reduction":  0,
            "basis":                   "rule_based",
        }

    # ── AI-suggester wrapper ──

    def _ai_actions(self,
                    gap: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Call ai_suggester_fn if injected; tag results basis=llm.
        Returns empty list on failure or no hook."""
        if self.ai_suggester_fn is None:
            return []
        try:
            ai_results = self.ai_suggester_fn(gap)
            if not isinstance(ai_results, list):
                logger.warning(
                    "ai_suggester_fn must return list; got "
                    f"{type(ai_results).__name__}")
                return []
            tagged = []
            for r in ai_results:
                if not isinstance(r, dict):
                    continue
                r_copy = dict(r)
                r_copy["basis"] = "llm"
                tagged.append(r_copy)
            return tagged
        except Exception as e:
            logger.warning(
                f"ai_suggester_fn raised {type(e).__name__}: {e}; "
                f"continuing without AI suggestions")
            return []

    # ── Prioritization ──

    def prioritize_actions(
            self,
            actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort actions by impact-per-cost ratio (descending).

        Per doc spec: prioritize by expected_gap_reduction /
        implementation_cost. Zero-cost actions sorted last (manual
        review actions). Returns new list; does not mutate input.
        """
        def ratio(a):
            cost = a.get("implementation_cost", 0)
            impact = a.get("expected_gap_reduction", 0)
            if not isinstance(cost, (int, float)) or cost <= 0:
                return -1  # sort last
            if not isinstance(impact, (int, float)):
                return 0
            return impact / cost

        # Sort: highest ratio first, manual review last
        return sorted(actions, key=ratio, reverse=True)

    # ── Per-gap pipeline ──

    def generate_corrective_actions(
            self, gap: Dict[str, Any]) -> Dict[str, Any]:
        """Generate corrective action plan for a single gap.

        Args:
            gap: gap dict from StrategyGapAnalyzer (must include
                root_cause.category, severity, gap, pillar, metric)

        Returns:
            {
              "gap_id":              str,
              "pillar":              str,
              "metric":              str,
              "severity":            str,
              "root_cause":          str,
              "recommended_actions": [...prioritized list],
              "combined_impact":     float (sum of expected_gap_reductions),
              "total_cost":          float (sum of implementation_costs),
              "n_actions":           int,
              "generated_at":        ISO-8601,
              "basis":               "rule_based" | "rule_based+llm",
            }
        """
        if not isinstance(gap, dict):
            return {
                "gap_id":              None,
                "recommended_actions": [],
                "combined_impact":     0,
                "total_cost":          0,
                "n_actions":           0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "basis":               "rule_based",
                "error":               "gap is not a dict",
            }

        rc = gap.get("root_cause", {})
        category = (rc.get("category") if isinstance(rc, dict)
                    else str(rc))

        actions: List[Dict[str, Any]] = []

        # Map root cause category to action template
        if category == "UNDER_RESOURCED":
            actions.append(self._resource_action(gap))
        elif category == "PROCESS_BOTTLENECK":
            actions.append(self._process_action(gap))
        elif category == "SKILL_GAP":
            actions.append(self._training_action(gap))
        elif category == "AI_CLASSIFIED":
            # AI-classified root cause without explicit type — manual review
            # PLUS the AI suggester gets a chance below
            actions.append(self._manual_review_action(gap))
        else:
            # UNCLASSIFIED or unknown
            actions.append(self._manual_review_action(gap))

        # AI-suggested additional actions (opt-in)
        actions.extend(self._ai_actions(gap))

        prioritized = self.prioritize_actions(actions)
        combined_impact = sum(
            a.get("expected_gap_reduction", 0) for a in prioritized)
        total_cost = sum(
            a.get("implementation_cost", 0) for a in prioritized)
        bases = sorted({a.get("basis", "rule_based") for a in prioritized})
        basis_label = "+".join(bases) if bases else "rule_based"

        # Generate gap_id if not present
        gap_id = (gap.get("gap_id")
                  or f"GAP-{gap.get('pillar', 'UNK')[:6].upper()}-"
                     f"{(gap.get('metric') or 'UNK')[:8].replace(' ', '')}")

        return {
            "gap_id":              gap_id,
            "pillar":              gap.get("pillar"),
            "metric":              gap.get("metric"),
            "severity":            gap.get("severity"),
            "root_cause":          category,
            "recommended_actions": prioritized,
            "combined_impact":     round(combined_impact, 4),
            "total_cost":          total_cost,
            "n_actions":           len(prioritized),
            "generated_at":        datetime.now(
                timezone.utc).isoformat(),
            "basis":               basis_label,
        }

    # ── Batch wrapper ──

    def generate_actions_for_all_gaps(
            self,
            gaps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate corrective actions for a full list of gaps.

        Args:
            gaps: list of gap dicts (from StrategyGapAnalyzer.analyze_gaps)

        Returns:
            {
              "action_plans":          [...one per gap],
              "n_gaps":                int,
              "n_total_actions":       int,
              "total_combined_impact": float,
              "total_cost":            float,
              "by_severity":           {HIGH: n, MEDIUM: n},
              "generated_at":          ISO-8601,
              "basis":                 "rule_based" | "rule_based+llm",
            }
        """
        action_plans = [self.generate_corrective_actions(g) for g in gaps]
        total_actions = sum(p["n_actions"] for p in action_plans)
        total_impact = sum(p["combined_impact"] for p in action_plans)
        total_cost = sum(p["total_cost"] for p in action_plans)

        by_severity = {"HIGH": 0, "MEDIUM": 0}
        for p in action_plans:
            sv = p.get("severity")
            if sv in by_severity:
                by_severity[sv] += 1

        all_bases = set()
        for p in action_plans:
            all_bases.update(p["basis"].split("+"))
        basis_label = "+".join(sorted(all_bases)) if all_bases else "rule_based"

        return {
            "action_plans":          action_plans,
            "n_gaps":                len(gaps),
            "n_total_actions":       total_actions,
            "total_combined_impact": round(total_impact, 4),
            "total_cost":            total_cost,
            "by_severity":           by_severity,
            "generated_at":          datetime.now(
                timezone.utc).isoformat(),
            "basis":                 basis_label,
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def generate_corrective_actions(gap: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper — instantiate generator and run."""
    return CorrectiveActionGenerator().generate_corrective_actions(gap)

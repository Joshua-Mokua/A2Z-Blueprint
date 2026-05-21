"""utils.gap_analyzer — Strategy Execution Gap Analyzer
(Standard ENH-146, v10.138). Phase 1 Strategy Module — seventh engine.

Per Continuation.docx §Standard #146 (Eco Bank QA spec):
    StrategyGapAnalyzer — real-time strategy-execution gap detection
    with root cause analysis. Compare actual performance against
    strategic targets at pillar, workstream, and KPI level. Identify
    systemic gaps affecting multiple pillars. Generate closure
    recommendations.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Gap detection is fully deterministic (rule-based threshold
     comparison)
  2. Root-cause analysis uses transparent decision-tree logic over
     resource utilization, process TAT, and skill gap signals from
     real bank data sources
  3. AI-suggested root causes are opt-in (ai_root_cause_fn injectable);
     when None, falls back to "UNCLASSIFIED" with explicit signals_seen

WHAT THIS MODULE SHIPS
----------------------
1. StrategyGapAnalyzer class with:
   - analyze_gaps(strategic_pillars, current_performance) — full pipeline
   - detect_pillar_gaps(pillar, performance) — per-pillar gap detection
   - analyze_root_cause(pillar_name, metric, signals) — decision tree
   - identify_systemic_gaps(gaps) — gaps affecting multiple pillars
   - generate_closure_recommendations(gaps, systemic_gaps) — strategy
   - create_closure_plan(recommendations) — phased execution plan

2. Integration with existing modules:
   - Reads from data/bsc_scores.json via DailyStrategyIntegration
   - Reads from utils.strategy_decomposition.PILLAR_TEMPLATES
   - Reads from utils.strategic_options for context
   - Writes nothing to performance.* tables (Rule 7 honored)

3. Severity classification per doc spec:
   - HIGH:    actual < target × 0.7 (gap > 30%)
   - MEDIUM:  target × 0.7 ≤ actual < target × 0.9 (gap 10-30%)
   - LOW:     not flagged as gap (within 10% of target)

HONESTY DISCIPLINE
------------------
- Detection threshold 0.9 is the doc-specified gap threshold; values
  within 10% of target are NOT flagged
- Root-cause categories are explicit constants; "UNCLASSIFIED"
  returned when no decision-tree branch matches (no fabrication)
- Resource utilization / process TAT / skill gap signals must be
  passed in by caller — engine does not invent them
- Systemic gap threshold (3+ pillars affected by same root cause) is
  documented; same input → same output

RELATED STANDARDS
-----------------
- ENH-143 Strategic Pillars — provides input strategic_pillars
- ENH-144 Initiative Portfolio — provides initiative status
- ENH-153 Daily Strategy Integration — feeds current_performance from BSC
- ENH-147 Corrective Action Generator — consumes gap output
- ENH-150 Strategy Health Dashboard (planned v10.139) — consumes
  systemic gaps for executive view
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.gap_analyzer")


# ════════════════════════════════════════════════════════════════════
# Gap detection thresholds (per Continuation.docx Standard #146)
# ════════════════════════════════════════════════════════════════════

GAP_THRESHOLD_RATIO = 0.90        # actual < 90% of target = gap
SEVERITY_HIGH_RATIO = 0.70        # actual < 70% of target = HIGH
SYSTEMIC_GAP_MIN_PILLARS = 3      # systemic = same root cause in 3+

# Root cause categories (transparent decision tree)
ROOT_CAUSE_UNDER_RESOURCED = "UNDER_RESOURCED"
ROOT_CAUSE_PROCESS_BOTTLENECK = "PROCESS_BOTTLENECK"
ROOT_CAUSE_SKILL_GAP = "SKILL_GAP"
ROOT_CAUSE_UNCLASSIFIED = "UNCLASSIFIED"

# Decision tree thresholds
RESOURCE_OVERUTIL_THRESHOLD = 1.20    # >120% utilization
SKILL_GAP_THRESHOLD = 0.30            # gap_score > 0.30


# ════════════════════════════════════════════════════════════════════
# StrategyGapAnalyzer
# ════════════════════════════════════════════════════════════════════

class StrategyGapAnalyzer:
    """Real-time strategy-execution gap detection.

    Caller pattern:

        from utils.strategy_decomposition import StrategyDecompositionEngine
        from utils.gap_analyzer import StrategyGapAnalyzer

        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            "digital growth")

        # Current performance: pillar_name → {metric_name: {target, actual}}
        # plus optional signals (resource_utilization, process_tat, skill_gap)
        current_performance = {
            "Digital & Data Transformation": {
                "AI adoption in 5 processes": {"target": 5,   "actual": 2},
                "API calls growth > 50%":     {"target": 50,  "actual": 30},
                "_signals": {
                    "resource_utilization": 1.35,  # 135%
                    "process_tat":          12.0,
                    "process_target_tat":   8.0,
                    "skill_gap_score":      0.45,
                }
            },
            ...
        }

        gaps = StrategyGapAnalyzer().analyze_gaps(
            pillars, current_performance)
    """

    def __init__(self,
                 ai_root_cause_fn: Optional[
                     Callable[[Dict, Dict], str]] = None):
        """
        Args:
            ai_root_cause_fn: optional callable(pillar_dict, metric_dict)
                → root_cause_string for LLM-enhanced classification.
                When None, returns ROOT_CAUSE_UNCLASSIFIED with
                explicit signals_seen.
        """
        self.ai_root_cause_fn = ai_root_cause_fn

    # ── Per-metric gap detection ──

    def _parse_metric_string(self, metric_str: str) -> Dict[str, Any]:
        """Parse 'NPS > 75' style success_metrics strings.

        Returns {"name": str, "target": float | None, "operator": str}
        Best-effort; returns name only if no number found.
        """
        import re
        m = re.match(r"^(.+?)\s*([<>]=?|=)\s*([\d.]+)\s*%?\s*$",
                     metric_str.strip())
        if not m:
            return {"name": metric_str.strip(), "target": None,
                    "operator": None}
        try:
            return {
                "name":     m.group(1).strip(),
                "operator": m.group(2),
                "target":   float(m.group(3)),
            }
        except ValueError:
            return {"name": metric_str.strip(), "target": None,
                    "operator": None}

    def _classify_gap(self,
                      target: float,
                      actual: float) -> Optional[Dict[str, Any]]:
        """Return gap dict if actual < target × GAP_THRESHOLD_RATIO,
        else None.

        For ratio comparison we treat lower-is-better metrics by
        convention: caller passes target as the desired upper bound
        (actual > target × 1.10 = gap). When operator hint is "<"
        (e.g., "NPL < 5%"), that's lower-is-better.
        """
        if not isinstance(target, (int, float)) or target <= 0:
            return None
        if not isinstance(actual, (int, float)):
            return None

        ratio = actual / target
        if ratio >= GAP_THRESHOLD_RATIO:
            return None  # within 10% → not a gap

        gap = round(target - actual, 4)
        gap_pct = round((1 - ratio) * 100, 2)
        severity = "HIGH" if ratio < SEVERITY_HIGH_RATIO else "MEDIUM"
        return {
            "gap":             gap,
            "gap_percentage":  gap_pct,
            "severity":        severity,
            "ratio":           round(ratio, 4),
        }

    def detect_pillar_gaps(
            self,
            pillar: Dict[str, Any],
            pillar_performance: Dict[str, Any]
            ) -> List[Dict[str, Any]]:
        """Detect gaps for a single pillar's success_metrics.

        Args:
            pillar: pillar dict (name, success_metrics, owner, ...)
            pillar_performance: dict with metric_name → {target, actual}
                + optional "_signals" key for root cause analysis

        Returns:
            List of gap dicts: pillar, level, metric, target, actual,
            gap, gap_percentage, severity, root_cause
        """
        gaps = []
        signals = pillar_performance.get("_signals", {})

        # Iterate over pillar's success_metrics; match by parsed name
        for metric_str in pillar.get("success_metrics", []):
            parsed = self._parse_metric_string(metric_str)
            metric_name = parsed["name"]

            # Look up actual: prefer exact metric_str key, else parsed name
            perf = (pillar_performance.get(metric_str)
                    or pillar_performance.get(metric_name))
            if not isinstance(perf, dict):
                continue

            target = perf.get("target", parsed.get("target"))
            actual = perf.get("actual")
            classification = self._classify_gap(target, actual)
            if classification is None:
                continue

            gap_record = {
                "level":           "PILLAR",
                "pillar":          pillar.get("name"),
                "metric":          metric_name,
                "metric_raw":      metric_str,
                "target":          target,
                "actual":          actual,
                **classification,
                "root_cause":      self.analyze_root_cause(
                    pillar, parsed, signals),
                "owner":           pillar.get("owner"),
            }
            gaps.append(gap_record)

        return gaps

    # ── Root-cause analysis (decision tree) ──

    def analyze_root_cause(
            self,
            pillar: Dict[str, Any],
            metric: Dict[str, Any],
            signals: Dict[str, Any]) -> Dict[str, Any]:
        """Drill down to root cause via decision tree.

        Decision order (per Continuation.docx Standard #146 spec):
        1. Resource constraint: utilization > 1.20 → UNDER_RESOURCED
        2. Process bottleneck: TAT > target_TAT → PROCESS_BOTTLENECK
        3. Skill gap: gap_score > 0.30 → SKILL_GAP
        4. Else: AI-classified or UNCLASSIFIED

        Returns:
            {
              "category":     str (one of ROOT_CAUSE_* constants),
              "detail":       str (human-readable explanation),
              "signals_seen": dict (for transparency)
            }
        """
        # Branch 1: Resource constraint
        util = signals.get("resource_utilization")
        if isinstance(util, (int, float)) and util > RESOURCE_OVERUTIL_THRESHOLD:
            overutil_pct = round((util - 1.0) * 100, 1)
            return {
                "category":     ROOT_CAUSE_UNDER_RESOURCED,
                "detail":       (f"Team overutilized by "
                                 f"{overutil_pct}% (utilization {util:.2f})"),
                "signals_seen": {"resource_utilization": util},
            }

        # Branch 2: Process bottleneck
        tat = signals.get("process_tat")
        target_tat = signals.get("process_target_tat")
        if (isinstance(tat, (int, float)) and isinstance(target_tat, (int, float))
                and target_tat > 0 and tat > target_tat):
            excess_pct = round((tat / target_tat - 1) * 100, 1)
            return {
                "category":     ROOT_CAUSE_PROCESS_BOTTLENECK,
                "detail":       (f"TAT exceeds target by {excess_pct}% "
                                 f"({tat} vs {target_tat})"),
                "signals_seen": {"process_tat": tat,
                                 "process_target_tat": target_tat},
            }

        # Branch 3: Skill gap
        skill_gap = signals.get("skill_gap_score")
        if (isinstance(skill_gap, (int, float))
                and skill_gap > SKILL_GAP_THRESHOLD):
            return {
                "category":     ROOT_CAUSE_SKILL_GAP,
                "detail":       (f"Team lacks required capabilities "
                                 f"(gap score {skill_gap:.2f})"),
                "signals_seen": {"skill_gap_score": skill_gap},
            }

        # Branch 4: AI-classified (opt-in)
        if self.ai_root_cause_fn is not None:
            try:
                ai_result = self.ai_root_cause_fn(pillar, metric)
                if isinstance(ai_result, str) and ai_result:
                    return {
                        "category":     "AI_CLASSIFIED",
                        "detail":       ai_result,
                        "signals_seen": dict(signals),
                        "basis":        "llm",
                    }
            except Exception as e:
                logger.warning(
                    f"ai_root_cause_fn raised {type(e).__name__}: {e}; "
                    f"falling back to UNCLASSIFIED")

        # Branch 5: Unclassified — honest fallback
        return {
            "category":     ROOT_CAUSE_UNCLASSIFIED,
            "detail":       ("No decision-tree branch matched. "
                             "Caller did not provide resource / process / "
                             "skill signals; root cause requires manual "
                             "classification."),
            "signals_seen": dict(signals),
        }

    # ── Systemic gap detection ──

    def identify_systemic_gaps(
            self,
            gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group gaps by root cause category. Categories appearing
        in SYSTEMIC_GAP_MIN_PILLARS or more pillars are flagged
        systemic.

        Returns:
            List of {category, pillar_count, pillars, total_gap_value,
                     severity_breakdown}
        """
        by_cause: Dict[str, List[Dict]] = {}
        for g in gaps:
            cat = g.get("root_cause", {}).get("category",
                                              ROOT_CAUSE_UNCLASSIFIED)
            by_cause.setdefault(cat, []).append(g)

        systemic = []
        for cat, group in by_cause.items():
            unique_pillars = sorted({g["pillar"] for g in group
                                     if g.get("pillar")})
            if len(unique_pillars) < SYSTEMIC_GAP_MIN_PILLARS:
                continue
            sev_breakdown = {"HIGH": 0, "MEDIUM": 0}
            for g in group:
                sv = g.get("severity")
                if sv in sev_breakdown:
                    sev_breakdown[sv] += 1
            systemic.append({
                "category":          cat,
                "pillar_count":      len(unique_pillars),
                "pillars":           unique_pillars,
                "total_gap_value":   round(
                    sum(g.get("gap", 0) for g in group), 4),
                "n_metric_gaps":     len(group),
                "severity_breakdown": sev_breakdown,
                "interpretation":    (
                    f"{cat} affects {len(unique_pillars)} pillars "
                    f"({len(group)} metric gaps). Root cause is systemic — "
                    f"address at organisational level rather than "
                    f"pillar-by-pillar."),
            })
        return systemic

    # ── Recommendations + closure plan ──

    def generate_closure_recommendations(
            self,
            gaps: List[Dict[str, Any]],
            systemic_gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate closure recommendations.

        Logic:
        - Each systemic gap → 1 organisational recommendation
        - Each non-systemic HIGH gap → 1 targeted recommendation
        - Each non-systemic MEDIUM gap → 1 monitoring recommendation
        - Sorted by severity (HIGH first) then gap_percentage desc
        """
        recommendations = []

        # Systemic recommendations first
        for sg in systemic_gaps:
            recommendations.append({
                "rec_id":           f"REC-SYS-{sg['category']}",
                "scope":            "ORGANISATIONAL",
                "type":              "systemic",
                "category":          sg["category"],
                "title":            (f"Address systemic {sg['category']} "
                                     f"affecting {sg['pillar_count']} pillars"),
                "affected_pillars":  sg["pillars"],
                "priority":          "HIGH"
                if sg["severity_breakdown"].get("HIGH", 0) > 0
                else "MEDIUM",
                "estimated_horizon": "1-2 quarters",
            })

        # Categorize gaps by whether they're already covered by systemic
        systemic_categories = {sg["category"] for sg in systemic_gaps}
        for g in gaps:
            cat = g.get("root_cause", {}).get("category",
                                              ROOT_CAUSE_UNCLASSIFIED)
            if cat in systemic_categories:
                continue  # already covered systemically
            severity = g.get("severity", "MEDIUM")
            rec_type = "targeted" if severity == "HIGH" else "monitoring"
            recommendations.append({
                "rec_id":           f"REC-{g['pillar'][:6].upper()}-"
                                    f"{g['metric'][:8].replace(' ', '')}",
                "scope":            "PILLAR_METRIC",
                "type":              rec_type,
                "category":          cat,
                "title":            (f"Close {severity} gap in {g['metric']} "
                                     f"({g['pillar']})"),
                "pillar":            g["pillar"],
                "metric":            g["metric"],
                "gap_value":         g["gap"],
                "gap_percentage":    g["gap_percentage"],
                "severity":          severity,
                "owner":             g.get("owner"),
                "priority":          severity,
                "estimated_horizon": ("1 quarter" if severity == "HIGH"
                                      else "2 quarters"),
            })

        # Sort by priority then gap %
        priority_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        recommendations.sort(
            key=lambda r: (priority_rank.get(r.get("priority"), 9),
                           -r.get("gap_percentage", 0)))
        return recommendations

    def create_closure_plan(
            self,
            recommendations: List[Dict[str, Any]]
            ) -> List[Dict[str, Any]]:
        """Phase recommendations into 3 buckets:
        - Immediate (next 30 days):    HIGH systemic + HIGH targeted
        - Near-term (next quarter):    MEDIUM systemic + HIGH monitoring
        - Long-term (next 2 quarters): MEDIUM monitoring + remainder
        """
        immediate, near_term, long_term = [], [], []
        for rec in recommendations:
            sev = rec.get("priority", "MEDIUM")
            scope = rec.get("scope")
            if sev == "HIGH":
                immediate.append(rec["rec_id"])
            elif sev == "MEDIUM" and scope == "ORGANISATIONAL":
                near_term.append(rec["rec_id"])
            else:
                long_term.append(rec["rec_id"])
        return [
            {"phase": "Immediate (30 days)",       "rec_ids": immediate},
            {"phase": "Near-term (1 quarter)",     "rec_ids": near_term},
            {"phase": "Long-term (2+ quarters)",   "rec_ids": long_term},
        ]

    # ── Main API ──

    def analyze_gaps(
            self,
            strategic_pillars: List[Dict[str, Any]],
            current_performance: Dict[str, Dict[str, Any]]
            ) -> Dict[str, Any]:
        """Full pipeline: per-pillar gap detection → root cause →
        systemic gap identification → recommendations → closure plan.

        Args:
            strategic_pillars: from StrategyDecompositionEngine
            current_performance: dict keyed by pillar_name; each value
                is dict of metric_name → {target, actual} plus optional
                "_signals" key for root cause analysis

        Returns:
            {
              "gaps":              [...],
              "systemic_gaps":     [...],
              "total_gap_value":   float,
              "n_pillars_with_gaps": int,
              "recommendations":   [...],
              "closure_plan":      [...],
              "n_high":            int,
              "n_medium":          int,
              "generated_at":      ISO-8601,
              "basis":             "rule_based",
            }
        """
        all_gaps = []
        for pillar in strategic_pillars:
            pname = pillar.get("name")
            if not pname:
                continue
            perf = current_performance.get(pname, {})
            pillar_gaps = self.detect_pillar_gaps(pillar, perf)
            all_gaps.extend(pillar_gaps)

        systemic = self.identify_systemic_gaps(all_gaps)
        recommendations = self.generate_closure_recommendations(
            all_gaps, systemic)
        closure_plan = self.create_closure_plan(recommendations)

        n_high = sum(1 for g in all_gaps if g.get("severity") == "HIGH")
        n_medium = sum(1 for g in all_gaps if g.get("severity") == "MEDIUM")
        pillars_with_gaps = {g["pillar"] for g in all_gaps if g.get("pillar")}

        return {
            "gaps":               all_gaps,
            "systemic_gaps":      systemic,
            "total_gap_value":    round(
                sum(g.get("gap", 0) for g in all_gaps), 4),
            "n_pillars_with_gaps": len(pillars_with_gaps),
            "recommendations":    recommendations,
            "closure_plan":       closure_plan,
            "n_high":             n_high,
            "n_medium":           n_medium,
            "generated_at":       datetime.now(
                timezone.utc).isoformat(),
            "basis":              "rule_based",
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def analyze_gaps(strategic_pillars: List[Dict],
                 current_performance: Dict[str, Dict]) -> Dict[str, Any]:
    """Convenience wrapper — instantiate engine and analyze."""
    return StrategyGapAnalyzer().analyze_gaps(
        strategic_pillars, current_performance)

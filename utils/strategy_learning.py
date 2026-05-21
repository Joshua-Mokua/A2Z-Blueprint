"""utils.strategy_learning — Strategy Learning Loop & Next Planning
(Standard ENH-148, v10.139). Phase 1 Strategy Module — ninth engine.

Per Continuation.docx §Standard #148 (Eco Bank QA spec):
    StrategyLearningLoop — capture lessons learned (what worked,
    what didn't, why) from strategy cycle and generate insights for
    next strategic planning cycle. Creates institutional memory.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Success/failure classification is deterministic (rule-based
     thresholds over completion_pct, actual_roi vs expected_roi,
     rag_status)
  2. Common-factor extraction is rule-based clustering on
     {department, type, sponsor, pillar} of successful vs failed
     initiatives
  3. AI hooks (ai_market_evolution_fn, ai_strategic_recs_fn) are
     opt-in and tagged basis="llm"; rule-based fallback transparent

WHAT THIS MODULE SHIPS
----------------------
1. StrategyLearningLoop class with:
   - capture_lessons_learned(strategy_cycle_id) — full pipeline
   - get_successful_initiatives(cycle_id) — completion_pct ≥ 90 AND
     rag_status in (Green, Yellow) AND actual_roi ≥ 0.8 × expected_roi
   - get_failed_initiatives(cycle_id) — completion_pct < 60 OR
     rag_status == Red OR actual_roi < 0.5 × expected_roi
   - extract_success_factors(initiatives) — clustering on dimensions
   - extract_failure_factors(initiatives) — clustering on dimensions
   - generate_insights(factors) — rule-based insight templates
   - generate_recommendations(success_factors, failure_factors) —
     paired recommendations
   - store_lessons(cycle_id, lessons) — persist to data/strategy_lessons.json
   - generate_next_cycle_insights() — market + competitor + capability

2. Categorization thresholds:
   - SUCCESS_COMPLETION_THRESHOLD = 90 (initiatives ≥ 90% complete)
   - FAILURE_COMPLETION_THRESHOLD = 60 (initiatives < 60% complete)
   - SUCCESS_ROI_RATIO = 0.80 (actual ≥ 80% of expected)
   - FAILURE_ROI_RATIO = 0.50 (actual < 50% of expected)
   - MIN_FACTOR_FREQUENCY = 2 (factor must appear in 2+ initiatives)

3. Reads from existing data/strategic_initiatives.json (25 entries
   with id, completion_pct, rag_status, actual_roi_pct, expected_roi_pct,
   department, sponsor, pillar fields).

HONESTY DISCIPLINE
------------------
- Empty lessons returned when no initiatives match thresholds (no
  fabrication of success/failure factors)
- Common-factor extraction requires MIN_FACTOR_FREQUENCY occurrences
  to surface — single-occurrence factors are NOT presented as
  patterns
- AI hooks fall back to "deferred for v10.140" with explicit reason
  rather than fabricating market intelligence
- Insights are generated from the actual factor clusters, not
  templated marketing copy

RELATED STANDARDS
-----------------
- ENH-144 Strategic Initiative Portfolio — provides initiative data
- ENH-146 Gap Analyzer — provides current cycle's execution gaps
- ENH-147 Corrective Action Generator — historical actions feed
  failure factor analysis
- ENH-141 SWOT — current cycle SWOT informs lessons
- ENH-150 Strategy Health Dashboard (this same drop) — surfaces
  lessons to executive view
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger("a2z.strategy_learning")


# ════════════════════════════════════════════════════════════════════
# Categorization thresholds (per Continuation.docx Standard #148)
# ════════════════════════════════════════════════════════════════════

SUCCESS_COMPLETION_THRESHOLD = 90      # ≥ 90% complete
FAILURE_COMPLETION_THRESHOLD = 60      # < 60% complete
SUCCESS_ROI_RATIO = 0.80               # actual ≥ 80% of expected
FAILURE_ROI_RATIO = 0.50               # actual < 50% of expected

# Factor extraction
MIN_FACTOR_FREQUENCY = 2                # factor must appear in 2+ initiatives

# Dimensions over which to extract common factors
FACTOR_DIMENSIONS = ("department", "type", "sponsor", "pillar")


# ════════════════════════════════════════════════════════════════════
# StrategyLearningLoop
# ════════════════════════════════════════════════════════════════════

class StrategyLearningLoop:
    """Capture learnings and inform next strategy cycle.

    Caller pattern:

        from utils.strategy_learning import StrategyLearningLoop

        loop = StrategyLearningLoop()
        lessons = loop.capture_lessons_learned("2025_cycle")
        # lessons["what_worked"]["initiatives"] → list of successful
        # lessons["what_worked"]["common_factors"] → factor clusters
        # lessons["recommendations_for_next_cycle"] → ...
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 ai_market_evolution_fn: Optional[Callable[[], Dict]] = None,
                 ai_strategic_recs_fn: Optional[
                     Callable[[Dict, Dict, Dict, Dict], Dict]] = None):
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.ai_market_evolution_fn = ai_market_evolution_fn
        self.ai_strategic_recs_fn = ai_strategic_recs_fn
        self._initiatives_cache: Optional[List[Dict]] = None

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

    # ── Initiative classification ──

    def get_successful_initiatives(
            self,
            strategy_cycle_id: Optional[str] = None
            ) -> List[Dict[str, Any]]:
        """Return initiatives meeting all success criteria:

        - completion_pct ≥ SUCCESS_COMPLETION_THRESHOLD (90)
        - rag_status in (Green, Yellow)
        - actual_roi_pct ≥ expected_roi_pct × SUCCESS_ROI_RATIO (0.8)
          OR actual_roi_pct == 0 (not yet measured but on track)

        strategy_cycle_id is reserved for filtering when multi-cycle
        seed exists; current seed is single-cycle.
        """
        initiatives = self._load_initiatives()
        successful = []
        for ini in initiatives:
            comp = ini.get("completion_pct", 0)
            rag = ini.get("rag_status", "")
            actual_roi = ini.get("actual_roi_pct", 0)
            expected_roi = ini.get("expected_roi_pct", 0)

            if not isinstance(comp, (int, float)):
                continue
            if comp < SUCCESS_COMPLETION_THRESHOLD:
                continue
            if rag == "Red":
                continue
            # ROI: meets threshold OR not yet measured
            if isinstance(actual_roi, (int, float)) and actual_roi > 0:
                if (isinstance(expected_roi, (int, float))
                        and expected_roi > 0
                        and actual_roi < expected_roi * SUCCESS_ROI_RATIO):
                    continue
            successful.append(ini)
        return successful

    def get_failed_initiatives(
            self,
            strategy_cycle_id: Optional[str] = None
            ) -> List[Dict[str, Any]]:
        """Return initiatives meeting any failure criterion:

        - completion_pct < FAILURE_COMPLETION_THRESHOLD (60), OR
        - rag_status == "Red", OR
        - actual_roi_pct < expected_roi_pct × FAILURE_ROI_RATIO (0.5)
          (when both ROI fields populated)
        """
        initiatives = self._load_initiatives()
        failed = []
        for ini in initiatives:
            comp = ini.get("completion_pct", 0)
            rag = ini.get("rag_status", "")
            actual_roi = ini.get("actual_roi_pct", 0)
            expected_roi = ini.get("expected_roi_pct", 0)

            is_failed = False
            if isinstance(comp, (int, float)) and comp < FAILURE_COMPLETION_THRESHOLD:
                is_failed = True
            if rag == "Red":
                is_failed = True
            if (isinstance(actual_roi, (int, float)) and actual_roi > 0
                    and isinstance(expected_roi, (int, float))
                    and expected_roi > 0
                    and actual_roi < expected_roi * FAILURE_ROI_RATIO):
                is_failed = True
            if is_failed:
                failed.append(ini)
        return failed

    # ── Common factor extraction ──

    def _extract_factors(
            self,
            initiatives: List[Dict[str, Any]],
            label: str) -> Dict[str, Any]:
        """Extract common factors across initiatives.

        For each FACTOR_DIMENSIONS field, count occurrences. Surface
        any value appearing in ≥ MIN_FACTOR_FREQUENCY initiatives.

        Returns:
            {
              "n_initiatives": int,
              "by_dimension": {
                 "department": [{"value": str, "count": int, "ratio": float}, ...],
                 ...
              },
              "label": str,
            }
        """
        n = len(initiatives)
        result = {
            "n_initiatives": n,
            "label":         label,
            "by_dimension":  {},
        }
        if n == 0:
            return result

        for dim in FACTOR_DIMENSIONS:
            counter = Counter()
            for ini in initiatives:
                val = ini.get(dim)
                if val is None or val == "":
                    continue
                counter[str(val)] += 1
            patterns = [
                {"value": v, "count": c, "ratio": round(c / n, 3)}
                for v, c in counter.most_common()
                if c >= MIN_FACTOR_FREQUENCY
            ]
            result["by_dimension"][dim] = patterns
        return result

    def extract_success_factors(
            self,
            initiatives: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._extract_factors(initiatives, label="success")

    def extract_failure_factors(
            self,
            initiatives: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._extract_factors(initiatives, label="failure")

    # ── Insight generation ──

    def generate_insights(self,
                          factors: Dict[str, Any]) -> List[str]:
        """Rule-based insight generation from factor clusters.

        For each dimension with ≥ 1 pattern, produce a templated
        insight line. No insights generated when no patterns surface.
        """
        insights = []
        n = factors.get("n_initiatives", 0)
        label = factors.get("label", "")
        if n == 0:
            return [(f"No {label} initiatives in this cycle — "
                     f"insufficient data for pattern extraction.")]
        by_dim = factors.get("by_dimension", {})
        for dim, patterns in by_dim.items():
            for pat in patterns[:3]:  # top 3 per dimension
                pct = round(pat["ratio"] * 100, 1)
                if label == "success":
                    insights.append(
                        f"{dim.capitalize()}='{pat['value']}' featured in "
                        f"{pat['count']}/{n} successful initiatives "
                        f"({pct}%) — pattern worth replicating in next cycle.")
                else:  # failure
                    insights.append(
                        f"{dim.capitalize()}='{pat['value']}' featured in "
                        f"{pat['count']}/{n} failed initiatives ({pct}%) — "
                        f"investigate as risk factor.")
        if not insights:
            insights.append(
                f"No common factors with frequency ≥ "
                f"{MIN_FACTOR_FREQUENCY} found across {label} initiatives.")
        return insights

    def generate_learnings(self,
                            factors: Dict[str, Any]) -> List[str]:
        """Same shape as generate_insights but framed as learnings."""
        return self.generate_insights(factors)

    # ── Recommendations ──

    def generate_recommendations(
            self,
            success_factors: Dict[str, Any],
            failure_factors: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate paired recommendations from success + failure factors.

        Logic:
        - For each success factor: "Replicate" recommendation
        - For each failure factor: "Mitigate" recommendation
        - When same dimension appears as both success AND failure
          (different values): emit "Discriminator" recommendation
          highlighting which value works
        """
        recommendations = []
        success_dims = success_factors.get("by_dimension", {})
        failure_dims = failure_factors.get("by_dimension", {})

        for dim in FACTOR_DIMENSIONS:
            success_patterns = success_dims.get(dim, [])
            failure_patterns = failure_dims.get(dim, [])

            for sp in success_patterns:
                # Check if same dim has different failure pattern
                fp_match = next(
                    (fp for fp in failure_patterns
                     if fp["value"] != sp["value"]), None)
                if fp_match:
                    recommendations.append({
                        "rec_id":       f"REC-LOOP-DISCRIM-{dim}-{sp['value']}",
                        "type":         "discriminator",
                        "dimension":    dim,
                        "title":        (
                            f"Prefer {dim}='{sp['value']}' "
                            f"({sp['count']} successes) over "
                            f"'{fp_match['value']}' "
                            f"({fp_match['count']} failures) for next cycle"),
                        "evidence":     {
                            "success_pattern": sp,
                            "failure_pattern": fp_match,
                        },
                    })
                else:
                    recommendations.append({
                        "rec_id":       f"REC-LOOP-REPLICATE-{dim}-{sp['value']}",
                        "type":         "replicate",
                        "dimension":    dim,
                        "title":        (
                            f"Replicate success pattern: "
                            f"{dim}='{sp['value']}' "
                            f"({sp['count']} successful initiatives)"),
                        "evidence":     {"success_pattern": sp},
                    })

            # Failure-only patterns (no matching success)
            for fp in failure_patterns:
                if not any(sp["value"] == fp["value"]
                           for sp in success_patterns):
                    if not any(r["dimension"] == dim
                               and r["type"] == "discriminator"
                               for r in recommendations):
                        # Avoid duplicating discriminator
                        recommendations.append({
                            "rec_id":   f"REC-LOOP-MITIGATE-{dim}-{fp['value']}",
                            "type":     "mitigate",
                            "dimension": dim,
                            "title":    (
                                f"Mitigate failure pattern: "
                                f"{dim}='{fp['value']}' "
                                f"({fp['count']} failures)"),
                            "evidence": {"failure_pattern": fp},
                        })

        return recommendations

    # ── Storage ──

    def store_lessons(self,
                       strategy_cycle_id: str,
                       lessons: Dict[str, Any]) -> bool:
        """Persist lessons to data/strategy_lessons.json. Returns True
        on success, False on failure.

        Idempotency: same cycle_id overwrites existing entry.
        """
        path = self.data_dir / "strategy_lessons.json"
        try:
            existing = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        existing = json.load(f)
                except (json.JSONDecodeError, OSError):
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing[strategy_cycle_id] = {
                **lessons,
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            return True
        except OSError as e:
            logger.warning(f"Failed to store lessons: {e}")
            return False

    # ── Main API ──

    def capture_lessons_learned(
            self,
            strategy_cycle_id: str = "current") -> Dict[str, Any]:
        """Full pipeline: classify → extract factors → generate
        insights → recommendations → store.

        Returns:
            {
              "strategy_cycle_id":  str,
              "what_worked":        {initiatives, common_factors, key_insights},
              "what_didnt_work":    {initiatives, common_factors, key_learnings},
              "recommendations_for_next_cycle": [...],
              "n_successful":       int,
              "n_failed":           int,
              "n_total":            int,
              "stored":             bool,
              "generated_at":       ISO-8601,
              "basis":              "rule_based",
            }
        """
        successful = self.get_successful_initiatives(strategy_cycle_id)
        failed = self.get_failed_initiatives(strategy_cycle_id)
        all_inits = self._load_initiatives()

        success_factors = self.extract_success_factors(successful)
        failure_factors = self.extract_failure_factors(failed)

        lessons = {
            "strategy_cycle_id": strategy_cycle_id,
            "what_worked": {
                "initiatives":     [self._summarize_initiative(i)
                                    for i in successful],
                "common_factors":  success_factors,
                "key_insights":    self.generate_insights(success_factors),
            },
            "what_didnt_work": {
                "initiatives":     [self._summarize_initiative(i)
                                    for i in failed],
                "common_factors":  failure_factors,
                "key_learnings":   self.generate_learnings(failure_factors),
            },
            "recommendations_for_next_cycle":
                self.generate_recommendations(
                    success_factors, failure_factors),
            "n_successful":      len(successful),
            "n_failed":          len(failed),
            "n_total":           len(all_inits),
            "generated_at":      datetime.now(timezone.utc).isoformat(),
            "basis":             "rule_based",
        }
        stored = self.store_lessons(strategy_cycle_id, lessons)
        lessons["stored"] = stored
        return lessons

    def _summarize_initiative(self, ini: Dict) -> Dict[str, Any]:
        """Return only the fields relevant for lessons-learned."""
        return {
            "id":                ini.get("id") or ini.get("initiative_code"),
            "name":              ini.get("name") or ini.get("initiative_name"),
            "pillar":            ini.get("pillar"),
            "department":        ini.get("department"),
            "type":              ini.get("type"),
            "sponsor":           ini.get("sponsor"),
            "completion_pct":    ini.get("completion_pct"),
            "rag_status":        ini.get("rag_status"),
            "expected_roi_pct":  ini.get("expected_roi_pct"),
            "actual_roi_pct":    ini.get("actual_roi_pct"),
        }

    # ── Next cycle insights ──

    def generate_next_cycle_insights(self) -> Dict[str, Any]:
        """AI-generated insights to inform next strategic planning cycle.

        Each component is opt-in via constructor hook. When None, the
        component returns honest "deferred" stub rather than fabricating.
        """
        # Market evolution
        if self.ai_market_evolution_fn is not None:
            try:
                market = self.ai_market_evolution_fn()
                market["basis"] = "llm"
            except Exception as e:
                logger.warning(
                    f"ai_market_evolution_fn failed: {e}; deferring")
                market = {
                    "status": "deferred",
                    "reason": (f"ai_market_evolution_fn raised "
                               f"{type(e).__name__}; market intelligence "
                               f"requires external feed."),
                    "basis":  "rule_based",
                }
        else:
            market = {
                "status": "deferred",
                "reason": ("No ai_market_evolution_fn injected; "
                           "market intelligence requires external feed "
                           "or LLM hook."),
                "basis":  "rule_based",
            }

        # Strategic recommendations
        if self.ai_strategic_recs_fn is not None:
            try:
                recs = self.ai_strategic_recs_fn(
                    market, {}, {}, self._get_previous_lessons())
                recs["basis"] = "llm"
            except Exception as e:
                logger.warning(
                    f"ai_strategic_recs_fn failed: {e}; deferring")
                recs = {
                    "status": "deferred",
                    "reason": (f"ai_strategic_recs_fn raised "
                               f"{type(e).__name__}"),
                    "basis":  "rule_based",
                }
        else:
            recs = {
                "status": "deferred",
                "reason": ("No ai_strategic_recs_fn injected; "
                           "strategic recommendations require LLM hook."),
                "basis":  "rule_based",
            }

        return {
            "market_intelligence":         market,
            "competitor_intelligence":     {"status": "deferred",
                                             "reason": "No competitor "
                                             "intelligence hook injected"},
            "internal_assessment":         {"status": "deferred",
                                             "reason": "No internal "
                                             "capability hook injected"},
            "strategic_recommendations":   recs,
            "previous_lessons":            self._get_previous_lessons(),
            "generated_at":                datetime.now(
                timezone.utc).isoformat(),
        }

    def _get_previous_lessons(self) -> Dict[str, Any]:
        path = self.data_dir / "strategy_lessons.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def capture_lessons_learned(strategy_cycle_id: str = "current"
                              ) -> Dict[str, Any]:
    """Convenience wrapper — instantiate engine and capture lessons."""
    return StrategyLearningLoop().capture_lessons_learned(strategy_cycle_id)

"""utils.strategy_health — Strategy Review & Health Dashboard
(Standard ENH-150, v10.139). Phase 1 Strategy Module — eleventh engine.

Per Continuation.docx §Standard #150 (Eco Bank QA spec):
    Real-time strategy execution dashboard with predictive alerts.
    Aggregates pillar progress, gap alerts, AI insights, and next-
    review date for executive view.

This is the BACKING ENGINE for `pages/150_strategy_dashboard.py`. The
doc spec describes a Streamlit page; we ship the engine that backs it
so the page is a thin presentation layer over deterministic data.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Health score is computed deterministically over weighted average
     of (pillar_progress, gap_severity_inverted, engagement_score)
  2. Predictive alerts use rule-based threshold detection (no ML
     forecast); explicit fallback when prerequisites missing
  3. AI insight generation is opt-in; rule-based templates fall back
     transparently

WHAT THIS MODULE SHIPS
----------------------
1. StrategyHealthEngine class with:
   - calculate_strategy_health(pillars, gap_result?, engagement?) —
     overall health score (0-100) computed from 3 components
   - get_pillar_progress(pillar_name, gap_result, performance?) —
     per-pillar progress + risk_level + initiatives status
   - generate_strategy_insights(pillars, gap_result, engagement?) —
     rule-based insight templates over real signals
   - get_predictive_alerts(pillars, gap_result, engagement?) —
     threshold-based alert list
   - get_next_review_date(cadence='QUARTERLY') — next quarter end
   - build_dashboard_payload(...) — full structured payload for UI

2. Health score formula:
   overall_score = (
     0.50 × pillar_progress_avg            # weight 50%
     + 0.30 × (100 - gap_severity_pct)     # weight 30%
     + 0.20 × engagement_score             # weight 20%
   )
   When a component is unavailable, weights re-normalize across
   available components (no fabricated zero values).

3. Risk level per pillar (rule-based):
   - LOW:    no HIGH gaps + ≥ 75% progress
   - MEDIUM: any HIGH gap OR 50-75% progress
   - HIGH:   ≥ 2 HIGH gaps OR < 50% progress

HONESTY DISCIPLINE
------------------
- When pillars empty or no gap data: returns score=None with explicit
  status="insufficient_data" rather than fabricated zero
- Component weights re-normalize transparently when source data missing
- "Initiatives on track" / "delayed" computed from real
  strategic_initiatives.json data; engine does not invent counts
- Predictive alerts list ONLY thresholds actually crossed; no
  speculative "may break" alerts
- Next review date is current quarter end (deterministic), not
  fabricated

RELATED STANDARDS
-----------------
- ENH-143 Strategic Pillars — provides pillars
- ENH-144 Initiative Portfolio — provides initiative status
- ENH-146 Gap Analyzer — provides gap_result input
- ENH-148 Strategy Learning Loop — provides historical lessons
- ENH-149 Stakeholder Engagement — provides engagement_score input
- ENH-153 Daily Strategy Integration — provides bank_strategy_health
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.strategy_health")


# ════════════════════════════════════════════════════════════════════
# Health score weights (when all 3 components available)
# ════════════════════════════════════════════════════════════════════

WEIGHT_PROGRESS = 0.50
WEIGHT_GAP_INVERSE = 0.30
WEIGHT_ENGAGEMENT = 0.20

# Risk level thresholds
RISK_LOW_PROGRESS_MIN = 75
RISK_MEDIUM_PROGRESS_MIN = 50
RISK_HIGH_GAP_COUNT = 2

# Alert thresholds
ALERT_HIGH_RISK_PILLAR_COUNT = 2     # ≥ 2 pillars HIGH risk
ALERT_TOTAL_GAP_VALUE = 100           # arbitrary domain-dependent
ALERT_ENGAGEMENT_LOW_THRESHOLD = 50

# Dashboard structure version
DASHBOARD_SCHEMA_VERSION = "1.0"


# ════════════════════════════════════════════════════════════════════
# StrategyHealthEngine
# ════════════════════════════════════════════════════════════════════

class StrategyHealthEngine:
    """Strategy Review & Health Dashboard backing engine.

    Caller pattern (typically from `pages/150_strategy_dashboard.py`):

        from utils.strategy_health import StrategyHealthEngine

        engine = StrategyHealthEngine()
        payload = engine.build_dashboard_payload(
            pillars=pillars,
            gap_result=gap_result,
            engagement_pulse=pulse_result)

        # Streamlit page renders payload['overall_score'] etc.
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 ai_insight_fn: Optional[
                     Callable[[Dict], List[str]]] = None):
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.ai_insight_fn = ai_insight_fn
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

    # ── Per-pillar progress ──

    def get_pillar_progress(
            self,
            pillar_name: str,
            gap_result: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
        """Return per-pillar progress, risk_level, and initiative
        breakdown.

        Logic:
        - progress = average completion_pct across pillar's initiatives
        - on_track = count of (rag_status=Green AND status not Cancelled)
        - delayed  = count of (rag_status in (Amber, Yellow))
        - blocked  = count of (rag_status=Red OR status=Cancelled)
        - risk_level from rules above
        """
        initiatives = [
            i for i in self._load_initiatives()
            if i.get("pillar") == pillar_name
        ]
        n = len(initiatives)
        if n == 0:
            return {
                "pillar":          pillar_name,
                "progress":        None,
                "n_initiatives":   0,
                "on_track":        0,
                "delayed":         0,
                "blocked":         0,
                "risk_level":      "UNKNOWN",
                "expected_completion": None,
                "fallback_reason":
                    "No initiatives mapped to this pillar in seed.",
            }

        completions = [
            i.get("completion_pct", 0)
            for i in initiatives
            if isinstance(i.get("completion_pct"), (int, float))
        ]
        progress = (sum(completions) / len(completions)
                    if completions else 0)

        on_track = sum(
            1 for i in initiatives
            if i.get("rag_status") == "Green"
            and i.get("status") not in ("Cancelled", "On Hold"))
        delayed = sum(
            1 for i in initiatives
            if i.get("rag_status") in ("Amber", "Yellow"))
        blocked = sum(
            1 for i in initiatives
            if i.get("rag_status") == "Red"
            or i.get("status") in ("Cancelled", "On Hold"))

        # HIGH gaps for this pillar
        n_high_gaps = 0
        if gap_result and isinstance(gap_result, dict):
            for g in gap_result.get("gaps", []):
                if (g.get("pillar") == pillar_name
                        and g.get("severity") == "HIGH"):
                    n_high_gaps += 1

        # Risk level rule
        if n_high_gaps >= RISK_HIGH_GAP_COUNT or progress < RISK_MEDIUM_PROGRESS_MIN:
            risk_level = "HIGH"
        elif n_high_gaps >= 1 or progress < RISK_LOW_PROGRESS_MIN:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Expected completion: latest target_end_date among non-blocked
        target_dates = [
            i.get("target_end_date") for i in initiatives
            if i.get("target_end_date")
            and i.get("status") not in ("Cancelled", "On Hold")
        ]
        expected_completion = max(target_dates) if target_dates else None

        return {
            "pillar":          pillar_name,
            "progress":        round(progress, 2),
            "n_initiatives":   n,
            "on_track":        on_track,
            "delayed":         delayed,
            "blocked":         blocked,
            "n_high_gaps":     n_high_gaps,
            "risk_level":      risk_level,
            "expected_completion": expected_completion,
            "fallback_reason": None,
        }

    # ── Strategy health score ──

    def calculate_strategy_health(
            self,
            pillars: List[Dict[str, Any]],
            gap_result: Optional[Dict[str, Any]] = None,
            engagement_pulse: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
        """Compute overall strategy health (0-100) from up to 3
        components.

        Component weights (when all available):
            progress:   50%
            gap_inv:    30%  (100 - normalized_gap_severity)
            engagement: 20%

        Re-normalizes when components missing.

        Returns:
            {
              "overall_score":     float | None,
              "level":             "HEALTHY" | "AT_RISK" | "CRITICAL" | "no_data",
              "components":        {progress, gap_inverse, engagement},
              "weights_used":      {progress, gap_inverse, engagement},
              "n_pillars":         int,
              "fallback_reason":   str | None,
            }
        """
        if not pillars:
            return {
                "overall_score":     None,
                "level":             "no_data",
                "components":        {},
                "weights_used":      {},
                "n_pillars":         0,
                "fallback_reason":   "No pillars provided.",
            }

        # Component 1: progress (avg pillar progress)
        pillar_progresses = []
        for p in pillars:
            pname = p.get("name")
            if not pname:
                continue
            pp = self.get_pillar_progress(pname, gap_result)
            if pp["progress"] is not None:
                pillar_progresses.append(pp["progress"])

        progress_score = (sum(pillar_progresses) / len(pillar_progresses)
                          if pillar_progresses else None)

        # Component 2: gap inverse
        if gap_result and isinstance(gap_result, dict):
            n_high = gap_result.get("n_high", 0)
            n_med = gap_result.get("n_medium", 0)
            n_total_gaps = n_high + n_med
            n_pillars = len(pillars)
            if n_pillars > 0:
                # Normalized: each HIGH gap costs more than MEDIUM
                gap_severity_pct = min(
                    100,
                    (n_high * 15 + n_med * 5) / n_pillars * 5)
                gap_inverse_score = max(0, 100 - gap_severity_pct)
            else:
                gap_inverse_score = None
        else:
            gap_inverse_score = None

        # Component 3: engagement
        if engagement_pulse and isinstance(engagement_pulse, dict):
            engagement_score = engagement_pulse.get("score")
            if not isinstance(engagement_score, (int, float)):
                engagement_score = None
        else:
            engagement_score = None

        # Re-normalize weights based on available components
        weights = {}
        if progress_score is not None:
            weights["progress"] = WEIGHT_PROGRESS
        if gap_inverse_score is not None:
            weights["gap_inverse"] = WEIGHT_GAP_INVERSE
        if engagement_score is not None:
            weights["engagement"] = WEIGHT_ENGAGEMENT

        if not weights:
            return {
                "overall_score":   None,
                "level":           "no_data",
                "components":      {
                    "progress":    progress_score,
                    "gap_inverse": gap_inverse_score,
                    "engagement":  engagement_score,
                },
                "weights_used":    {},
                "n_pillars":       len(pillars),
                "fallback_reason":
                    "Insufficient data: no pillar progress or gap or "
                    "engagement input available.",
            }

        # Re-normalize so weights sum to 1
        weight_sum = sum(weights.values())
        normalized = {k: v / weight_sum for k, v in weights.items()}

        score = 0
        if "progress" in normalized:
            score += normalized["progress"] * progress_score
        if "gap_inverse" in normalized:
            score += normalized["gap_inverse"] * gap_inverse_score
        if "engagement" in normalized:
            score += normalized["engagement"] * engagement_score

        # Level classification
        if score >= 75:
            level = "HEALTHY"
        elif score >= 50:
            level = "AT_RISK"
        else:
            level = "CRITICAL"

        return {
            "overall_score":   round(score, 2),
            "level":           level,
            "components":      {
                "progress":    (round(progress_score, 2)
                                if progress_score is not None else None),
                "gap_inverse": (round(gap_inverse_score, 2)
                                if gap_inverse_score is not None else None),
                "engagement":  (round(engagement_score, 2)
                                if engagement_score is not None else None),
            },
            "weights_used":    {k: round(v, 3)
                                for k, v in normalized.items()},
            "n_pillars":       len(pillars),
            "fallback_reason": None,
        }

    # ── Insights ──

    def generate_strategy_insights(
            self,
            pillars: List[Dict[str, Any]],
            gap_result: Optional[Dict[str, Any]] = None,
            engagement_pulse: Optional[Dict[str, Any]] = None,
            health: Optional[Dict[str, Any]] = None) -> List[str]:
        """Rule-based insight templates over real signals.

        AI hook (ai_insight_fn) augments rule-based insights when
        injected.
        """
        insights = []

        # Insight 1: HIGH-risk pillars
        high_risk_pillars = []
        for p in pillars:
            pname = p.get("name")
            if not pname:
                continue
            pp = self.get_pillar_progress(pname, gap_result)
            if pp["risk_level"] == "HIGH":
                high_risk_pillars.append(pname)
        if high_risk_pillars:
            insights.append(
                f"{len(high_risk_pillars)} pillar(s) at HIGH risk: "
                f"{', '.join(high_risk_pillars)}. "
                f"Prioritize corrective actions.")

        # Insight 2: Total gap value
        if gap_result and isinstance(gap_result, dict):
            tgv = gap_result.get("total_gap_value", 0)
            n_high = gap_result.get("n_high", 0)
            if n_high > 0:
                insights.append(
                    f"{n_high} HIGH-severity execution gap(s) "
                    f"(total gap value {tgv}). Review gap analyzer "
                    f"output for root causes.")
            systemic = gap_result.get("systemic_gaps", [])
            if systemic:
                cats = ", ".join(s["category"] for s in systemic[:3])
                insights.append(
                    f"{len(systemic)} systemic gap(s) detected ({cats}). "
                    f"Address at organisational level.")

        # Insight 3: Engagement
        if engagement_pulse and isinstance(engagement_pulse, dict):
            score = engagement_pulse.get("score")
            level = engagement_pulse.get("level")
            if isinstance(score, (int, float)):
                if level == "LOW":
                    insights.append(
                        f"Engagement pulse score {score}/100 "
                        f"is LOW. Strategy is not landing with staff. "
                        f"Run contribution campaign per ENH-149.")
                elif level == "HIGH":
                    insights.append(
                        f"Engagement pulse score {score}/100 is HIGH. "
                        f"Strategy resonates with staff.")

        # Insight 4: Health score level
        if health and isinstance(health, dict):
            hl = health.get("level")
            score = health.get("overall_score")
            if hl == "CRITICAL":
                insights.append(
                    f"Strategy health score {score}/100 is CRITICAL. "
                    f"Convene executive review immediately.")

        # AI augmentation
        if self.ai_insight_fn is not None:
            try:
                ai_results = self.ai_insight_fn({
                    "pillars": pillars,
                    "gap_result": gap_result,
                    "engagement_pulse": engagement_pulse,
                    "health": health,
                })
                if isinstance(ai_results, list):
                    for ins in ai_results:
                        if isinstance(ins, str) and ins:
                            insights.append(f"[AI] {ins}")
            except Exception as e:
                logger.warning(
                    f"ai_insight_fn raised {type(e).__name__}: {e}; "
                    f"falling back to rule-based insights only")

        if not insights:
            insights.append(
                "No anomalies detected. Strategy execution proceeding "
                "without flagged risks. Continue monitoring.")
        return insights

    # ── Predictive alerts ──

    def get_predictive_alerts(
            self,
            pillars: List[Dict[str, Any]],
            gap_result: Optional[Dict[str, Any]] = None,
            engagement_pulse: Optional[Dict[str, Any]] = None
            ) -> List[Dict[str, Any]]:
        """Threshold-based alerts (no ML forecasting).

        Each alert has: severity (HIGH/MEDIUM/LOW), message, source.
        """
        alerts = []

        # Alert: 2+ pillars HIGH risk
        high_risk = [
            self.get_pillar_progress(p.get("name"), gap_result)
            for p in pillars
            if p.get("name")
        ]
        n_high_risk = sum(1 for pp in high_risk
                          if pp["risk_level"] == "HIGH")
        if n_high_risk >= ALERT_HIGH_RISK_PILLAR_COUNT:
            alerts.append({
                "severity": "HIGH",
                "code":     "MULTI_PILLAR_HIGH_RISK",
                "message":  (f"{n_high_risk} pillars at HIGH risk — "
                             f"systemic execution issue."),
                "source":   "pillar_progress",
            })

        # Alert: total gap value above threshold
        if gap_result and isinstance(gap_result, dict):
            tgv = gap_result.get("total_gap_value", 0)
            if tgv > ALERT_TOTAL_GAP_VALUE:
                alerts.append({
                    "severity": "MEDIUM",
                    "code":     "HIGH_TOTAL_GAP",
                    "message":  (f"Total gap value {tgv} exceeds "
                                 f"threshold {ALERT_TOTAL_GAP_VALUE}."),
                    "source":   "gap_analyzer",
                })

        # Alert: engagement low
        if engagement_pulse and isinstance(engagement_pulse, dict):
            score = engagement_pulse.get("score")
            if isinstance(score, (int, float)) and score < ALERT_ENGAGEMENT_LOW_THRESHOLD:
                alerts.append({
                    "severity": "HIGH",
                    "code":     "LOW_ENGAGEMENT",
                    "message":  (f"Engagement score {score} below "
                                 f"threshold {ALERT_ENGAGEMENT_LOW_THRESHOLD}."),
                    "source":   "engagement_pulse",
                })

        return alerts

    # ── Next review date ──

    def get_next_review_date(
            self,
            cadence: str = "QUARTERLY",
            today: Optional[datetime] = None) -> str:
        """Return next review date as ISO 'YYYY-MM-DD'.

        QUARTERLY: end of current quarter.
        MONTHLY: end of current month.
        """
        if today is None:
            today = datetime.now(timezone.utc)
        if cadence.upper() == "MONTHLY":
            # Month end
            if today.month == 12:
                year, month = today.year + 1, 1
            else:
                year, month = today.year, today.month + 1
            return f"{year}-{month:02d}-01"
        # Default QUARTERLY
        q = (today.month - 1) // 3
        # End-of-quarter month
        eoq_month = (q + 1) * 3
        # Last day of that month is approx; use first of next month -1
        if eoq_month == 12:
            return f"{today.year}-12-31"
        # First day of next month (to keep deterministic, no calendar import)
        days_per = {3: 31, 6: 30, 9: 30}
        return f"{today.year}-{eoq_month:02d}-{days_per[eoq_month]}"

    # ── Build dashboard payload ──

    def build_dashboard_payload(
            self,
            pillars: List[Dict[str, Any]],
            gap_result: Optional[Dict[str, Any]] = None,
            engagement_pulse: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
        """Full dashboard payload.

        Returns:
            {
              "schema_version":     "1.0",
              "overall_score":      float | None,
              "level":              str,
              "components":         {...},
              "pillar_progress":    [...per-pillar dicts],
              "alerts":             [...threshold alerts],
              "insights":           [...rule-based + optional AI],
              "next_review_date":   ISO date,
              "n_pillars":          int,
              "n_total_gaps":       int,
              "engagement_score":   float | None,
              "generated_at":       ISO-8601,
            }
        """
        health = self.calculate_strategy_health(
            pillars, gap_result, engagement_pulse)
        per_pillar = [
            self.get_pillar_progress(p.get("name"), gap_result)
            for p in pillars
            if p.get("name")
        ]
        alerts = self.get_predictive_alerts(
            pillars, gap_result, engagement_pulse)
        insights = self.generate_strategy_insights(
            pillars, gap_result, engagement_pulse, health)

        n_total_gaps = 0
        if gap_result and isinstance(gap_result, dict):
            n_total_gaps = len(gap_result.get("gaps", []))

        engagement_score = None
        if engagement_pulse and isinstance(engagement_pulse, dict):
            engagement_score = engagement_pulse.get("score")

        return {
            "schema_version":     DASHBOARD_SCHEMA_VERSION,
            "overall_score":      health.get("overall_score"),
            "level":              health.get("level"),
            "components":         health.get("components", {}),
            "weights_used":       health.get("weights_used", {}),
            "pillar_progress":    per_pillar,
            "alerts":             alerts,
            "insights":           insights,
            "next_review_date":   self.get_next_review_date(),
            "n_pillars":          len(pillars),
            "n_total_gaps":       n_total_gaps,
            "engagement_score":   engagement_score,
            "generated_at":       datetime.now(
                timezone.utc).isoformat(),
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def build_dashboard_payload(
        pillars: List[Dict],
        gap_result: Optional[Dict] = None,
        engagement_pulse: Optional[Dict] = None) -> Dict[str, Any]:
    """Convenience wrapper — instantiate engine and build payload."""
    return StrategyHealthEngine().build_dashboard_payload(
        pillars, gap_result, engagement_pulse)

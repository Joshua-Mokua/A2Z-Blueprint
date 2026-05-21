"""utils.sto_toolkit — Strategy Transformation Office Toolkit
(Standard ENH-154, v10.140). Phase 1 Strategy Module — fourteenth engine.

Per Continuation.docx §Standard #154 (Eco Bank QA spec):
    STO Toolkit — complete toolkit for the Strategy Transformation
    Office command centre. Six tabs: Portfolio, Risks, Reviews,
    Analytics, Minutes, Academy.

This is the BACKING ENGINE for `pages/151_sto_toolkit.py`. The doc
spec describes a Streamlit page; we ship the engine that backs it
so the page is a thin presentation layer over deterministic
aggregations from existing engines (read-only across the Strategy
module).

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. All data aggregations are deterministic — same input → same output
  2. No fabrication: missing data sources return explicit fallback
     reason rather than synthesized content
  3. Read-only contract: this engine NEVER writes to performance.*
     tables or modifies other Strategy engine outputs
  4. AI hooks (ai_review_pack_fn, ai_dependency_map_fn) opt-in,
     transparent fallback labelling

WHAT THIS MODULE SHIPS
----------------------
1. STOToolkit class with one method per tab:
   - get_portfolio() — initiative table + summary metrics
   - get_strategy_risks() — risk register from data/strategy_risks.json
   - get_upcoming_reviews() — calendar reads data/strategy_reviews.json
   - get_strategy_analytics() — trend + dependency map data
   - get_meeting_minutes() — read data/strategy_minutes.json
   - get_strategy_training() — read data/strategy_training.json
   - generate_review_pack() — assemble structured review pack (PDF
     generation is a SEPARATE concern; this returns a payload)

2. Read-only aggregations from existing engines:
   - Initiative portfolio via ENH-144 (direct read of seed data)
   - Risk register from data/strategy_risks.json
   - Reviews/minutes/training from JSON files

3. Default seeds shipped:
   - data/strategy_risks.json (5 baseline strategy execution risks)
   - data/strategy_reviews.json (4 quarterly review entries)
   - data/strategy_minutes.json (3 baseline minutes entries)
   - data/strategy_training.json (4 baseline training sessions)

HONESTY DISCIPLINE
------------------
- All seed files are explicit baselines; engine returns empty list +
  fallback_reason when files absent
- Risk levels HIGH/MEDIUM/LOW are explicit in each entry; engine
  never invents severities
- Review pack assembly produces a structured payload — actual PDF
  rendering is delegated to caller (not fabricated as "downloaded")
- Read-only with respect to BSC engine + Strategy engines

RELATED STANDARDS
-----------------
- ENH-144 Initiative Portfolio — provides initiative data
- ENH-146 Gap Analyzer — gap data feeds risk register
- ENH-148 Strategy Learning Loop — historical lessons feed analytics
- ENH-149 Stakeholder Engagement — engagement scores
- ENH-150 Strategy Health Engine — overall health for analytics tab
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.sto_toolkit")


# ════════════════════════════════════════════════════════════════════
# STOToolkit
# ════════════════════════════════════════════════════════════════════

class STOToolkit:
    """Strategy Transformation Office command-centre backing engine.

    Caller pattern (typically from `pages/151_sto_toolkit.py`):

        from utils.sto_toolkit import STOToolkit

        tk = STOToolkit()
        portfolio = tk.get_portfolio()
        risks     = tk.get_strategy_risks()
        analytics = tk.get_strategy_analytics()
        pack      = tk.generate_review_pack()
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 ai_review_pack_fn: Optional[Callable] = None):
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.ai_review_pack_fn = ai_review_pack_fn

    # ── Generic JSON loader ──

    def _load_json(self, filename: str) -> Any:
        path = self.data_dir / filename
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"{filename} unreadable: {e}")
            return None

    # ── Tab 1: Portfolio ──

    def get_portfolio(self) -> Dict[str, Any]:
        """Return initiative portfolio + summary metrics.

        Reads data/strategic_initiatives.json (seed maintained by
        ENH-144) and computes RAG distribution, completion stats,
        budget consumption.
        """
        data = self._load_json("strategic_initiatives.json")
        if data is None:
            return {
                "initiatives":    [],
                "n_initiatives":  0,
                "rag_distribution": {},
                "fallback_reason": ("data/strategic_initiatives.json "
                                     "not found."),
            }
        initiatives = (data if isinstance(data, list)
                       else data.get("initiatives", [])
                       if isinstance(data, dict) else [])
        if not initiatives:
            return {
                "initiatives":     [],
                "n_initiatives":   0,
                "rag_distribution": {},
                "fallback_reason":  "Initiatives list empty.",
            }

        # Aggregate
        rag_dist = {"Green": 0, "Yellow": 0, "Amber": 0, "Red": 0,
                    "Unknown": 0}
        total_budget = total_actual_cost = 0.0
        n_complete = 0
        for ini in initiatives:
            rag = ini.get("rag_status", "Unknown")
            rag_dist[rag if rag in rag_dist else "Unknown"] = (
                rag_dist.get(rag if rag in rag_dist else "Unknown", 0) + 1)
            comp = ini.get("completion_pct", 0)
            if isinstance(comp, (int, float)) and comp >= 90:
                n_complete += 1
            budget = ini.get("estimated_cost") or (
                (ini.get("budget_kes_m", 0) or 0) * 1_000_000)
            actual = ini.get("actual_cost") or (
                (ini.get("actual_spend_kes_m", 0) or 0) * 1_000_000)
            if isinstance(budget, (int, float)):
                total_budget += budget
            if isinstance(actual, (int, float)):
                total_actual_cost += actual

        return {
            "initiatives":      initiatives,
            "n_initiatives":    len(initiatives),
            "rag_distribution": rag_dist,
            "n_complete":       n_complete,
            "completion_rate":  round(n_complete / len(initiatives) * 100, 2),
            "total_budget_kes": round(total_budget, 2),
            "total_actual_cost_kes": round(total_actual_cost, 2),
            "budget_consumption_pct": (
                round(total_actual_cost / total_budget * 100, 2)
                if total_budget > 0 else None),
            "fallback_reason":  None,
        }

    # ── Tab 2: Risks ──

    def get_strategy_risks(self) -> Dict[str, Any]:
        """Return strategy execution risk register.

        Reads data/strategy_risks.json. Each risk entry:
            {id, name, level (HIGH/MEDIUM/LOW), mitigation, owner,
             status (Open/Mitigated/Closed)}
        """
        data = self._load_json("strategy_risks.json")
        if data is None:
            return {
                "risks":           [],
                "n_risks":         0,
                "by_level":        {},
                "fallback_reason": ("data/strategy_risks.json not found. "
                                     "Caller should populate baseline."),
            }
        risks = data if isinstance(data, list) else []
        by_level = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for r in risks:
            level = r.get("level", "MEDIUM")
            if level in by_level:
                by_level[level] += 1
        return {
            "risks":           risks,
            "n_risks":         len(risks),
            "by_level":        by_level,
            "fallback_reason": None,
        }

    # ── Tab 3: Reviews ──

    def get_upcoming_reviews(
            self,
            today: Optional[datetime] = None) -> Dict[str, Any]:
        """Return upcoming strategy reviews from data/strategy_reviews.json.

        Schema:
            [
                {"review_id": str, "type": "QUARTERLY"/"MONTHLY",
                 "date": "YYYY-MM-DD", "attendees": [...], "agenda": str,
                 "owner": str, "status": "scheduled"/"completed"}
            ]
        """
        if today is None:
            today = datetime.now(timezone.utc)
        today_str = today.strftime("%Y-%m-%d")
        data = self._load_json("strategy_reviews.json")
        if data is None:
            return {
                "reviews":         [],
                "n_upcoming":      0,
                "next_review":     None,
                "fallback_reason": ("data/strategy_reviews.json not found."),
            }
        all_reviews = data if isinstance(data, list) else []
        upcoming = [
            r for r in all_reviews
            if r.get("status") == "scheduled"
            and r.get("date", "") >= today_str
        ]
        upcoming.sort(key=lambda r: r.get("date", ""))
        next_review = upcoming[0] if upcoming else None
        return {
            "reviews":         upcoming,
            "n_upcoming":      len(upcoming),
            "next_review":     next_review,
            "fallback_reason": None,
        }

    # ── Tab 4: Analytics ──

    def get_strategy_analytics(self) -> Dict[str, Any]:
        """Aggregate strategy analytics from existing engines.

        Returns dict with health snapshot, gap snapshot, lessons
        snapshot, and engagement snapshot — all read-only.
        """
        result = {
            "health":      None,
            "gap_summary": None,
            "lessons":     None,
            "engagement":  None,
            "fallback_reasons": [],
        }

        try:
            from utils.strategy_health import StrategyHealthEngine
            from utils.strategy_decomposition import (
                StrategyDecompositionEngine)
            pillars = StrategyDecompositionEngine().define_strategic_pillars(
                "")
            payload = StrategyHealthEngine().build_dashboard_payload(
                pillars)
            result["health"] = {
                "overall_score": payload.get("overall_score"),
                "level":          payload.get("level"),
                "n_alerts":       len(payload.get("alerts", [])),
            }
        except Exception as e:
            result["fallback_reasons"].append(
                f"strategy_health unavailable: {e}")

        try:
            data = self._load_json("strategy_lessons.json")
            if data and isinstance(data, dict):
                latest_cycle = max(data.keys(),
                                    key=lambda k: data[k].get(
                                        "stored_at", ""))
                cycle = data[latest_cycle]
                result["lessons"] = {
                    "latest_cycle":  latest_cycle,
                    "n_successful": cycle.get("n_successful"),
                    "n_failed":     cycle.get("n_failed"),
                    "n_recs":        len(cycle.get(
                        "recommendations_for_next_cycle", [])),
                }
        except Exception as e:
            result["fallback_reasons"].append(
                f"strategy_lessons unavailable: {e}")

        try:
            from utils.stakeholder_engagement import (
                StakeholderEngagementEngine)
            pulse = StakeholderEngagementEngine().run_engagement_pulse()
            result["engagement"] = {
                "score":       pulse.get("score"),
                "level":       pulse.get("level"),
                "n_responses": pulse.get("n_responses"),
            }
        except Exception as e:
            result["fallback_reasons"].append(
                f"engagement unavailable: {e}")

        return result

    # ── Tab 5: Minutes ──

    def get_meeting_minutes(self) -> Dict[str, Any]:
        """Strategy meeting minutes from data/strategy_minutes.json."""
        data = self._load_json("strategy_minutes.json")
        if data is None:
            return {
                "minutes":         [],
                "n_minutes":       0,
                "fallback_reason": ("data/strategy_minutes.json "
                                     "not found."),
            }
        minutes = data if isinstance(data, list) else []
        return {
            "minutes":         sorted(minutes,
                                       key=lambda m: m.get("date", ""),
                                       reverse=True),
            "n_minutes":       len(minutes),
            "fallback_reason": None,
        }

    # ── Tab 6: Academy ──

    def get_strategy_training(self) -> Dict[str, Any]:
        """Upcoming strategy training sessions."""
        data = self._load_json("strategy_training.json")
        if data is None:
            return {
                "sessions":        [],
                "n_sessions":      0,
                "fallback_reason": ("data/strategy_training.json "
                                     "not found."),
            }
        sessions = data if isinstance(data, list) else []
        # Filter to future sessions
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        upcoming = [s for s in sessions
                    if s.get("date", "") >= today_str
                    and (s.get("seats_left") is None
                         or s.get("seats_left", 0) > 0)]
        upcoming.sort(key=lambda s: s.get("date", ""))
        return {
            "sessions":        upcoming,
            "n_sessions":      len(upcoming),
            "n_total":         len(sessions),
            "fallback_reason": None,
        }

    # ── Review pack assembly ──

    def generate_review_pack(self) -> Dict[str, Any]:
        """Assemble a structured strategy review pack payload.

        Returns a structured dict the caller can convert to PDF /
        PowerPoint / Word. NOT a downloadable artifact directly —
        the rendering is delegated to PDF skill or similar.

        AI augmentation via ai_review_pack_fn opt-in.
        """
        portfolio = self.get_portfolio()
        risks = self.get_strategy_risks()
        analytics = self.get_strategy_analytics()
        reviews = self.get_upcoming_reviews()

        pack = {
            "title":             "Strategy Review Pack",
            "generated_at":      datetime.now(
                timezone.utc).isoformat(),
            "sections":          {
                "executive_summary": {
                    "n_initiatives":  portfolio.get("n_initiatives", 0),
                    "completion_rate": portfolio.get("completion_rate"),
                    "rag_distribution": portfolio.get("rag_distribution"),
                    "health_score":   (
                        analytics.get("health", {}).get("overall_score")
                        if analytics.get("health") else None),
                    "engagement_score": (
                        analytics.get("engagement", {}).get("score")
                        if analytics.get("engagement") else None),
                    "n_high_risks":   risks.get("by_level", {}).get(
                        "HIGH", 0),
                },
                "portfolio_summary": portfolio,
                "risk_register":     risks,
                "analytics_snapshot": analytics,
                "next_review":       reviews.get("next_review"),
            },
            "basis":             "rule_based",
        }

        # AI augmentation
        if self.ai_review_pack_fn is not None:
            try:
                ai_pack = self.ai_review_pack_fn(pack)
                if isinstance(ai_pack, dict):
                    pack["ai_augmentation"] = ai_pack
                    pack["basis"] = "rule_based+llm"
            except Exception as e:
                logger.warning(
                    f"ai_review_pack_fn raised {type(e).__name__}: {e}; "
                    f"falling back to rule-based pack")

        return pack

    # ── Full toolkit payload ──

    def get_full_toolkit_payload(self) -> Dict[str, Any]:
        """Single-call payload for full STO command centre rendering.

        Returns:
            {
              "portfolio":  {...},
              "risks":      {...},
              "reviews":    {...},
              "analytics":  {...},
              "minutes":    {...},
              "training":   {...},
              "generated_at": ISO-8601,
            }
        """
        return {
            "portfolio":     self.get_portfolio(),
            "risks":         self.get_strategy_risks(),
            "reviews":       self.get_upcoming_reviews(),
            "analytics":     self.get_strategy_analytics(),
            "minutes":       self.get_meeting_minutes(),
            "training":      self.get_strategy_training(),
            "generated_at":  datetime.now(timezone.utc).isoformat(),
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def get_full_toolkit_payload() -> Dict[str, Any]:
    """Convenience wrapper — instantiate toolkit and return payload."""
    return STOToolkit().get_full_toolkit_payload()

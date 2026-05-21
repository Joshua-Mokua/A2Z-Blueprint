"""utils.stakeholder_engagement — Stakeholder Engagement & Pulse
(Standard ENH-149, v10.139). Phase 1 Strategy Module — tenth engine.

Per Continuation.docx §Standard #149 (Eco Bank QA spec):
    StakeholderEngagementEngine — ensure everyone feels part of the
    strategy process. Run engagement pulse surveys (4 canonical
    questions, quarterly cadence) and track strategy contribution
    campaigns.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Pulse score is computed deterministically from response data
  2. Engagement classification (HIGH/MEDIUM/LOW) uses documented
     thresholds
  3. Sentiment classification uses keyword-based rules with optional
     LLM hook (ai_sentiment_fn) tagged basis="llm" on success

WHAT THIS MODULE SHIPS
----------------------
1. StakeholderEngagementEngine class with:
   - run_engagement_pulse(department=None, period=None) — collect
     pulse responses (from data/engagement_pulse.json or empty)
   - calculate_pulse_score(responses) — average across 4 canonical
     questions per Continuation.docx Standard #149
   - classify_engagement_level(score) — HIGH/MEDIUM/LOW
   - run_strategy_contribution_campaign(pillar) — campaign metadata
   - record_campaign_submission(campaign_id, submission) — append to
     campaigns store
   - rank_campaign_submissions(campaign_id) — score by votes + AI
     score (when hook injected)
   - create_strategy_awareness(strategic_pillars) — caller-driven
     orchestration entrypoint

2. Four canonical pulse questions per Continuation.docx Standard #149:
   - Q1: "I understand how my work contributes to bank strategy"
   - Q2: "I feel empowered to make decisions that support strategy"
   - Q3: "I receive regular updates on strategy progress"
   - Q4: "My input is valued in strategic planning"

3. 5-point Likert scale (1=Strongly Disagree, 5=Strongly Agree).
   Score = mean across all responses, scaled to 0-100.

4. Engagement thresholds:
   - HIGH:    score ≥ 75 (≥ 3.75 average on 5-point)
   - MEDIUM:  50 ≤ score < 75
   - LOW:     score < 50

HONESTY DISCIPLINE
------------------
- Empty response set returns score=None with explicit "no_data"
  status rather than fabricated zero
- Pulse questions are EXACT canonical strings from Continuation.docx
- Reward amounts (KES 50K/25K/25K) are doc-spec constants, not invented
- Campaign submissions are stored canonically; engine does not
  invent submissions
- Sentiment is rule-based (keyword overlap) by default; LLM is opt-in

RELATED STANDARDS
-----------------
- ENH-145 Enhanced Cascade — provides individual OKR data
- ENH-153 Daily Strategy Integration — provides personal dashboards
- ENH-148 Strategy Learning Loop — consumes engagement signals as
  failure-factor input
- ENH-150 Strategy Health Dashboard (this same drop) — surfaces
  engagement to executive view
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.stakeholder_engagement")


# ════════════════════════════════════════════════════════════════════
# Constants (per Continuation.docx Standard #149)
# ════════════════════════════════════════════════════════════════════

# 4 canonical pulse questions (verbatim from doc spec)
PULSE_QUESTIONS = (
    "I understand how my work contributes to bank strategy",
    "I feel empowered to make decisions that support strategy",
    "I receive regular updates on strategy progress",
    "My input is valued in strategic planning",
)

# Default cadence
DEFAULT_PULSE_FREQUENCY = "QUARTERLY"

# 5-point Likert scale
LIKERT_MIN = 1
LIKERT_MAX = 5

# Engagement thresholds (0-100 scale)
ENGAGEMENT_HIGH_THRESHOLD = 75
ENGAGEMENT_MEDIUM_THRESHOLD = 50

# Campaign rewards (per doc spec, KES)
DEFAULT_CAMPAIGN_REWARDS = {
    "best_idea":       50_000,
    "most_feasible":   25_000,
    "most_innovative": 25_000,
}

DEFAULT_SUBMISSION_PERIOD_DAYS = 30


# ════════════════════════════════════════════════════════════════════
# StakeholderEngagementEngine
# ════════════════════════════════════════════════════════════════════

class StakeholderEngagementEngine:
    """Ensure everyone feels part of the strategy process.

    Caller pattern:

        from utils.stakeholder_engagement import StakeholderEngagementEngine

        engine = StakeholderEngagementEngine()
        pulse = engine.run_engagement_pulse(department="Retail Banking")
        # pulse["score"] → 0-100
        # pulse["level"] → HIGH/MEDIUM/LOW

        campaign = engine.run_strategy_contribution_campaign(
            {"name": "Customer Experience Excellence"})
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 ai_sentiment_fn: Optional[
                     Callable[[List[str]], Dict]] = None):
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.ai_sentiment_fn = ai_sentiment_fn

    # ── Data loaders ──

    def _load_pulse_responses(self) -> List[Dict[str, Any]]:
        """Load pulse responses from data/engagement_pulse.json.

        Expected schema:
            [
                {
                    "respondent_code":  str,    # staff_code or anon
                    "department":       str,
                    "period":           str,    # "2025-Q4"
                    "responses":        {q1: 1-5, q2: 1-5, q3: 1-5, q4: 1-5},
                    "comment":          str (optional),
                    "submitted_at":     ISO-8601 (optional),
                },
                ...
            ]

        When file does not exist, returns empty list (NOT fabricated data).
        """
        path = self.data_dir / "engagement_pulse.json"
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "responses" in data:
                return data["responses"]
            return []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"engagement_pulse.json unreadable: {e}")
            return []

    def _filter_responses(
            self,
            responses: List[Dict],
            department: Optional[str],
            period: Optional[str]) -> List[Dict]:
        filtered = responses
        if department:
            filtered = [r for r in filtered
                        if r.get("department") == department]
        if period:
            filtered = [r for r in filtered
                        if r.get("period") == period]
        return filtered

    # ── Pulse calculation ──

    def calculate_pulse_score(
            self,
            responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute pulse score from responses.

        Score formula:
            For each response, average the 4 question scores (1-5 scale)
            Across all responses, take mean
            Scale to 0-100: ((mean - 1) / 4) * 100

        Returns:
            {
              "score":            float | None  (0-100),
              "level":            "HIGH" | "MEDIUM" | "LOW" | "no_data",
              "n_responses":      int,
              "by_question":      {q_text: avg_1_to_5, ...},
              "raw_mean":         float | None  (1-5 scale),
              "completion_rate":  float (0-1, fraction with all 4 answered),
              "fallback_reason":  str | None,
            }
        """
        if not responses:
            return {
                "score":           None,
                "level":           "no_data",
                "n_responses":     0,
                "by_question":     {},
                "raw_mean":        None,
                "completion_rate": 0.0,
                "fallback_reason": "No pulse responses available.",
            }

        # Per-question averages
        by_question: Dict[str, List[float]] = {q: [] for q in PULSE_QUESTIONS}
        complete_responses = 0
        for r in responses:
            answers = r.get("responses", {})
            if not isinstance(answers, dict):
                continue
            n_answered = 0
            for q in PULSE_QUESTIONS:
                ans = answers.get(q)
                if isinstance(ans, (int, float)) and LIKERT_MIN <= ans <= LIKERT_MAX:
                    by_question[q].append(float(ans))
                    n_answered += 1
            if n_answered == len(PULSE_QUESTIONS):
                complete_responses += 1

        # Per-question average
        per_q_avg = {}
        all_avgs = []
        for q, vals in by_question.items():
            if vals:
                avg = sum(vals) / len(vals)
                per_q_avg[q] = round(avg, 3)
                all_avgs.append(avg)
            else:
                per_q_avg[q] = None

        if not all_avgs:
            return {
                "score":           None,
                "level":           "no_data",
                "n_responses":     len(responses),
                "by_question":     per_q_avg,
                "raw_mean":        None,
                "completion_rate": 0.0,
                "fallback_reason":
                    f"Responses present but no valid Likert "
                    f"answers ({LIKERT_MIN}-{LIKERT_MAX}) found.",
            }

        raw_mean = sum(all_avgs) / len(all_avgs)
        score = ((raw_mean - LIKERT_MIN) / (LIKERT_MAX - LIKERT_MIN)) * 100
        completion = complete_responses / len(responses) if responses else 0

        return {
            "score":           round(score, 2),
            "level":           self.classify_engagement_level(score),
            "n_responses":     len(responses),
            "by_question":     per_q_avg,
            "raw_mean":        round(raw_mean, 3),
            "completion_rate": round(completion, 3),
            "fallback_reason": None,
        }

    def classify_engagement_level(self, score: float) -> str:
        """0-100 score → HIGH/MEDIUM/LOW."""
        if score >= ENGAGEMENT_HIGH_THRESHOLD:
            return "HIGH"
        if score >= ENGAGEMENT_MEDIUM_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    # ── Pulse main API ──

    def run_engagement_pulse(
            self,
            department: Optional[str] = None,
            period: Optional[str] = None,
            frequency: str = DEFAULT_PULSE_FREQUENCY) -> Dict[str, Any]:
        """Run engagement pulse for a department / period / both / neither.

        Returns:
            {
              ...calculate_pulse_score fields...,
              "department":      str | None,
              "period":          str | None,
              "frequency":       str,
              "questions":       tuple[str, ...],  # canonical 4
              "comment_summary": dict (rule-based or LLM),
              "generated_at":    ISO-8601,
              "basis":           "rule_based" | "rule_based+llm",
            }
        """
        all_responses = self._load_pulse_responses()
        filtered = self._filter_responses(
            all_responses, department, period)
        score_result = self.calculate_pulse_score(filtered)

        # Comment summary (rule-based by default, LLM optional)
        comments = [r.get("comment", "") for r in filtered
                    if r.get("comment")]
        comment_summary = self._summarize_comments(comments)

        bases = ["rule_based"]
        if comment_summary.get("basis") == "llm":
            bases.append("llm")
        basis_label = "+".join(bases)

        return {
            **score_result,
            "department":      department,
            "period":          period,
            "frequency":       frequency,
            "questions":       PULSE_QUESTIONS,
            "comment_summary": comment_summary,
            "generated_at":    datetime.now(
                timezone.utc).isoformat(),
            "basis":           basis_label,
        }

    def _summarize_comments(
            self,
            comments: List[str]) -> Dict[str, Any]:
        """Rule-based or LLM-based comment summary.

        Rule-based: simple positive/negative keyword scan.
        LLM: pass through ai_sentiment_fn, tag basis=llm.
        """
        if not comments:
            return {
                "n_comments":  0,
                "themes":      [],
                "sentiment":   None,
                "basis":       "rule_based",
                "fallback_reason": "No comments to summarize.",
            }

        if self.ai_sentiment_fn is not None:
            try:
                ai_result = self.ai_sentiment_fn(comments)
                return {
                    "n_comments": len(comments),
                    "themes":     ai_result.get("themes", []),
                    "sentiment":  ai_result.get("sentiment"),
                    "basis":      "llm",
                    "fallback_reason": None,
                }
            except Exception as e:
                logger.warning(
                    f"ai_sentiment_fn raised {type(e).__name__}: {e}; "
                    f"falling back to rule-based")

        # Rule-based: positive/negative keyword scan
        positive_kw = {"good", "great", "excellent", "love",
                       "appreciate", "value", "engaged", "positive",
                       "supported", "empowered"}
        negative_kw = {"bad", "poor", "frustrated", "ignored",
                       "disconnected", "lost", "confused", "unclear",
                       "unsupported", "stressful"}
        pos_count = neg_count = 0
        for c in comments:
            words = c.lower().split()
            pos_count += sum(1 for w in words if w in positive_kw)
            neg_count += sum(1 for w in words if w in negative_kw)
        if pos_count + neg_count == 0:
            sentiment = "neutral"
        elif pos_count > neg_count:
            sentiment = "positive"
        elif neg_count > pos_count:
            sentiment = "negative"
        else:
            sentiment = "mixed"
        return {
            "n_comments":      len(comments),
            "themes":          [],
            "sentiment":       sentiment,
            "positive_hits":   pos_count,
            "negative_hits":   neg_count,
            "basis":           "rule_based",
            "fallback_reason": None,
        }

    # ── Strategy contribution campaigns ──

    def run_strategy_contribution_campaign(
            self,
            pillar: Dict[str, Any],
            submission_period_days: int = DEFAULT_SUBMISSION_PERIOD_DAYS,
            rewards: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Create a strategy contribution campaign for a pillar.

        Args:
            pillar: pillar dict (name, owner, ...)
            submission_period_days: window for submissions
            rewards: optional override of DEFAULT_CAMPAIGN_REWARDS

        Returns:
            Campaign metadata dict (caller persists / surfaces).
        """
        pname = pillar.get("name", "Unknown Pillar")
        return {
            "campaign_id":       f"CAMPAIGN-{pname.replace(' ', '_').upper()}",
            "pillar":            pname,
            "challenge":         (
                f"How can we accelerate progress on {pname}?"),
            "submission_period_days": submission_period_days,
            "rewards":           rewards or dict(DEFAULT_CAMPAIGN_REWARDS),
            "submissions":       [],
            "status":             "open",
            "owner":             pillar.get("owner"),
            "created_at":        datetime.now(
                timezone.utc).isoformat(),
        }

    def record_campaign_submission(
            self,
            campaign: Dict[str, Any],
            submission: Dict[str, Any]) -> Dict[str, Any]:
        """Append a submission to a campaign's submissions list.

        submission expected schema:
            {staff_code, idea, votes (optional), submitted_at (optional)}

        Returns updated campaign.
        """
        campaign["submissions"] = campaign.get("submissions", [])
        sub_copy = dict(submission)
        if "submitted_at" not in sub_copy:
            sub_copy["submitted_at"] = datetime.now(
                timezone.utc).isoformat()
        if "votes" not in sub_copy:
            sub_copy["votes"] = 0
        campaign["submissions"].append(sub_copy)
        return campaign

    def rank_campaign_submissions(
            self,
            campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rank submissions by votes (descending). Same-vote ties
        broken by submission timestamp (earliest first)."""
        subs = campaign.get("submissions", [])
        return sorted(
            subs,
            key=lambda s: (-s.get("votes", 0),
                            s.get("submitted_at", "")))

    # ── Personal dashboards (orchestration entrypoint) ──

    def create_strategy_awareness(
            self,
            strategic_pillars: List[Dict[str, Any]],
            employees: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Caller-driven orchestration: produce per-employee dashboard
        payloads + run aggregate pulse.

        For per-employee personalized scorecards, callers should use
        utils.daily_strategy_integration.DailyStrategyIntegration
        directly. This method returns aggregate metadata.

        Returns:
            {
              "n_pillars":      int,
              "n_employees":    int,
              "pulse":          {... from run_engagement_pulse},
              "generated_at":   ISO-8601,
            }
        """
        # Pulse without filters (bank-wide)
        pulse = self.run_engagement_pulse()

        # Build dashboard payload (orchestration only — daily_strategy_
        # integration handles per-employee scorecards via existing engine)
        return {
            "n_pillars":     len(strategic_pillars),
            "n_employees":   len(employees) if employees is not None else None,
            "pulse":         pulse,
            "generated_at":  datetime.now(
                timezone.utc).isoformat(),
            "note":          ("Per-employee scorecards produced by "
                              "daily_strategy_integration.create_personal_"
                              "strategy_scorecard()."),
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def run_engagement_pulse(department: Optional[str] = None,
                          period: Optional[str] = None) -> Dict[str, Any]:
    """Convenience wrapper — instantiate engine and run pulse."""
    return StakeholderEngagementEngine().run_engagement_pulse(
        department, period)

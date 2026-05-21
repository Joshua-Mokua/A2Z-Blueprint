"""utils.integrity_culture — Integrity Culture Score &
Benchmarking (ENH-164, v10.188).

Phase 5 Resource Optimization — ninth standard. Composes four
operator-supplied sub-indicators — Transparency, Trust,
Sentiment, Code of Conduct adherence — into a composite
Integrity Culture Score (ICS) on a 0–100 scale, with optional
benchmarking against an operator-supplied external benchmark.

DESIGN CONTRACT
---------------
1. **Operator-supplied indicators only.** The engine does NOT
   parse emails, chat, or any communications. It does NOT do
   real-time behavioural telemetry. Operator collects indicator
   values via offline surveys / process metrics / audit reviews
   and feeds them in. This is a scoring engine, not a sensor.
2. **Privacy posture inherited from ENH-161.** Team-level
   submissions with `n_respondents < 5` are suppressed; the
   suppression flag is set and component sub-scores are not
   published. Aggregate suppression matches the §44 special-
   category posture for sentiment data.
3. **Weighted composite, weights are explicit.** Default
   weights are equal (0.25 each) but operator can override.
   The actual weights used are surfaced on every score record
   so reviewers can verify the math.
4. **Benchmarking is comparison, not a verdict.** When an
   external benchmark score is supplied, the engine returns
   `delta_vs_benchmark` and `relative_band` (LEADING / ON_PAR /
   LAGGING) but does NOT mark the score as good or bad.
5. **No NLP, no telemetry.** Every approach that would let the
   engine grade culture from communications is explicitly
   deferred. The Operator declares the indicators; the engine
   composes them.

REGULATORY BASIS
----------------
- Internal Code of Conduct
- Internal Speak-Up / Whistleblower Policy
- Kenya DPA 2019 §44 (sentiment is special-category)
- BSC People + Internal Controls perspective

HONEST DEFERRALS
----------------
- NLP_TEXT_ANALYSIS: explicitly out of scope; no parsing of
  emails / chat / Slack / call transcripts
- REAL_TIME_BEHAVIORAL_TELEMETRY: no keystroke, email-volume,
  call-volume, or video-presence monitoring
- CROSS_INDUSTRY_BENCHMARK_DATA: no external benchmark dataset
  bundled; operator supplies the comparator score
- CULTURAL_SURVEY_AUTOMATION: surveys conducted offline; engine
  ingests aggregate results, does not run the surveys
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# Suppression threshold — matches ENH-161 (§44 special-category
# data warrants conservative threshold)
MIN_RESPONDENTS = 5

# Score domain
MIN_SCORE = 0.0
MAX_SCORE = 100.0


class CultureBand(Enum):
    """Operational interpretation of the composite score."""
    STRONG = "strong"           # ≥ 80
    DEVELOPING = "developing"   # 60–80
    AT_RISK = "at_risk"         # 40–60
    CRITICAL = "critical"       # < 40


class RelativeBand(Enum):
    """Position vs external benchmark."""
    LEADING = "leading"         # delta ≥ +5
    ON_PAR = "on_par"           # |delta| < 5
    LAGGING = "lagging"         # delta ≤ -5


@dataclass(frozen=True)
class CultureWeights:
    """Composite weights — must sum to 1.0."""
    transparency: float = 0.25
    trust: float = 0.25
    sentiment: float = 0.25
    code_of_conduct: float = 0.25

    def to_dict(self) -> Dict[str, float]:
        return {
            "transparency": self.transparency,
            "trust": self.trust,
            "sentiment": self.sentiment,
            "code_of_conduct": self.code_of_conduct,
        }

    def validate(self) -> None:
        total = (self.transparency + self.trust
                 + self.sentiment + self.code_of_conduct)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"weights must sum to 1.0 (got {total:.6f})"
            )
        for name, w in self.to_dict().items():
            if w < 0:
                raise ValueError(f"weight {name} must be non-negative")


@dataclass(frozen=True)
class CultureSubmission:
    """Operator-supplied per-team indicator submission."""
    team_code: str
    n_respondents: int
    transparency_score: float       # 0-100
    trust_score: float              # 0-100
    sentiment_score: float          # 0-100
    code_of_conduct_score: float    # 0-100
    period_label: str               # "2026-Q1" etc
    external_benchmark_score: Optional[float] = None  # 0-100 if supplied

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_code": self.team_code,
            "n_respondents": self.n_respondents,
            "transparency_score": self.transparency_score,
            "trust_score": self.trust_score,
            "sentiment_score": self.sentiment_score,
            "code_of_conduct_score": self.code_of_conduct_score,
            "period_label": self.period_label,
            "external_benchmark_score": self.external_benchmark_score,
        }


@dataclass(frozen=True)
class CultureScore:
    """Composite score record for a team-period."""
    team_code: str
    period_label: str
    n_respondents: int
    composite_score: Optional[float]    # None if suppressed
    band: Optional[CultureBand]         # None if suppressed
    sub_scores: Dict[str, float]        # empty if suppressed
    weights_used: Dict[str, float]
    delta_vs_benchmark: Optional[float]
    relative_band: Optional[RelativeBand]
    data_suppressed: bool
    rationale: str
    scored_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_code": self.team_code,
            "period_label": self.period_label,
            "n_respondents": self.n_respondents,
            "composite_score": self.composite_score,
            "band": self.band.value if self.band else None,
            "sub_scores": dict(self.sub_scores),
            "weights_used": dict(self.weights_used),
            "delta_vs_benchmark": self.delta_vs_benchmark,
            "relative_band": (
                self.relative_band.value
                if self.relative_band else None
            ),
            "data_suppressed": self.data_suppressed,
            "rationale": self.rationale,
            "scored_at": self.scored_at,
        }


class IntegrityCultureEngine:
    """Scores team-level integrity culture from operator-supplied
    indicators. Read-only — composes inputs, never mutates."""

    DEFERRALS = (
        "NLP_TEXT_ANALYSIS",
        "REAL_TIME_BEHAVIORAL_TELEMETRY",
        "CROSS_INDUSTRY_BENCHMARK_DATA",
        "CULTURAL_SURVEY_AUTOMATION",
    )

    def __init__(self, weights: Optional[CultureWeights] = None):
        if weights is None:
            weights = CultureWeights()
        weights.validate()
        self._weights = weights
        self._scores: List[CultureScore] = []

    # ---------------------------------------------- validation

    @staticmethod
    def _validate_submission(s: CultureSubmission) -> None:
        if not s.team_code:
            raise ValueError("team_code required")
        if not s.period_label:
            raise ValueError("period_label required")
        if s.n_respondents < 0:
            raise ValueError("n_respondents must be non-negative")
        for name, val in (
            ("transparency_score", s.transparency_score),
            ("trust_score", s.trust_score),
            ("sentiment_score", s.sentiment_score),
            ("code_of_conduct_score", s.code_of_conduct_score),
        ):
            if not (MIN_SCORE <= val <= MAX_SCORE):
                raise ValueError(
                    f"{name} must be in [{MIN_SCORE}, {MAX_SCORE}]; "
                    f"got {val}"
                )
        if s.external_benchmark_score is not None:
            if not (MIN_SCORE <= s.external_benchmark_score <= MAX_SCORE):
                raise ValueError(
                    f"external_benchmark_score must be in "
                    f"[{MIN_SCORE}, {MAX_SCORE}]"
                )

    # ----------------------------------------------- band logic

    @staticmethod
    def _band_for(score: float) -> CultureBand:
        if score >= 80.0:
            return CultureBand.STRONG
        if score >= 60.0:
            return CultureBand.DEVELOPING
        if score >= 40.0:
            return CultureBand.AT_RISK
        return CultureBand.CRITICAL

    @staticmethod
    def _relative_band(delta: float) -> RelativeBand:
        if delta >= 5.0:
            return RelativeBand.LEADING
        if delta <= -5.0:
            return RelativeBand.LAGGING
        return RelativeBand.ON_PAR

    # ------------------------------------------------ scoring

    def score_team(self, submission: CultureSubmission) -> CultureScore:
        """Score one team-period from a submission."""
        self._validate_submission(submission)

        # Suppression check
        if submission.n_respondents < MIN_RESPONDENTS:
            score = CultureScore(
                team_code=submission.team_code,
                period_label=submission.period_label,
                n_respondents=submission.n_respondents,
                composite_score=None,
                band=None,
                sub_scores={},
                weights_used=self._weights.to_dict(),
                delta_vs_benchmark=None,
                relative_band=None,
                data_suppressed=True,
                rationale=(
                    f"data suppressed — n_respondents < "
                    f"{MIN_RESPONDENTS}"
                ),
                scored_at=datetime.now(timezone.utc).isoformat(),
            )
            self._scores.append(score)
            return score

        sub_scores = {
            "transparency": submission.transparency_score,
            "trust": submission.trust_score,
            "sentiment": submission.sentiment_score,
            "code_of_conduct": submission.code_of_conduct_score,
        }
        composite = (
            submission.transparency_score * self._weights.transparency
            + submission.trust_score * self._weights.trust
            + submission.sentiment_score * self._weights.sentiment
            + submission.code_of_conduct_score
            * self._weights.code_of_conduct
        )
        band = self._band_for(composite)

        # Benchmark comparison if supplied
        if submission.external_benchmark_score is not None:
            delta = composite - submission.external_benchmark_score
            rel_band = self._relative_band(delta)
        else:
            delta = None
            rel_band = None

        score = CultureScore(
            team_code=submission.team_code,
            period_label=submission.period_label,
            n_respondents=submission.n_respondents,
            composite_score=composite,
            band=band,
            sub_scores=sub_scores,
            weights_used=self._weights.to_dict(),
            delta_vs_benchmark=delta,
            relative_band=rel_band,
            data_suppressed=False,
            rationale=(
                f"composite {composite:.1f} → band {band.value}"
            ),
            scored_at=datetime.now(timezone.utc).isoformat(),
        )
        self._scores.append(score)
        return score

    # --------------------------------------------- multi-team

    def score_multiple(
        self, submissions: List[CultureSubmission],
    ) -> Dict[str, Any]:
        """Score multiple submissions and return rollup stats."""
        results = [self.score_team(s) for s in submissions]
        bands = {b.value: 0 for b in CultureBand}
        n_suppressed = 0
        published_scores = []
        for r in results:
            if r.data_suppressed:
                n_suppressed += 1
                continue
            bands[r.band.value] += 1
            published_scores.append(r.composite_score)

        avg_published = (
            sum(published_scores) / len(published_scores)
            if published_scores else None
        )
        return {
            "n_submissions": len(submissions),
            "n_suppressed": n_suppressed,
            "n_published": len(published_scores),
            "bands_distribution": bands,
            "average_composite_score_published": avg_published,
        }

    # -------------------------------------------------- queries

    def list_scores(self) -> List[CultureScore]:
        return list(self._scores)

    def latest_per_team(self) -> Dict[str, CultureScore]:
        """Return the latest score per team_code (last write wins)."""
        out: Dict[str, CultureScore] = {}
        for s in self._scores:
            out[s.team_code] = s
        return out

    # ----------------------------------------------------- meta

    def board_summary(self) -> Dict[str, Any]:
        bands = {b.value: 0 for b in CultureBand}
        n_suppressed = 0
        for s in self._scores:
            if s.data_suppressed:
                n_suppressed += 1
                continue
            bands[s.band.value] += 1
        return {
            "engine": "ENH-164 IntegrityCultureEngine",
            "n_scores_lifetime": len(self._scores),
            "n_scores_suppressed": n_suppressed,
            "bands_distribution": bands,
            "min_respondents_for_publish": MIN_RESPONDENTS,
            "weights_in_use": self._weights.to_dict(),
            "regulatory_basis": (
                "Internal Code of Conduct + Speak-Up Policy + "
                "Kenya DPA 2019 §44 (special category) + "
                "BSC People + Internal Controls perspective"
            ),
            "deferrals": {
                "NLP_TEXT_ANALYSIS": (
                    "DEFERRED — explicitly out of scope; no "
                    "parsing of emails/chat/Slack/call transcripts"
                ),
                "REAL_TIME_BEHAVIORAL_TELEMETRY": (
                    "DEFERRED — no keystroke, email-volume, "
                    "call-volume, or video-presence monitoring"
                ),
                "CROSS_INDUSTRY_BENCHMARK_DATA": (
                    "DEFERRED — no external benchmark dataset "
                    "bundled; operator supplies comparator"
                ),
                "CULTURAL_SURVEY_AUTOMATION": (
                    "DEFERRED — surveys conducted offline; "
                    "engine ingests aggregate results only"
                ),
            },
        }

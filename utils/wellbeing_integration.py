"""utils.wellbeing_integration — Wellbeing & Burnout Early Warning
Integration Engine (ENH-161, v10.185).

Phase 5 Resource Optimization — sixth standard. Sits ABOVE the
existing per-individual `utils.wellness.WellnessEngine` (Standard
#19) and composes it with ENH-160 utilization signals to surface
**team-level** early warning signals while protecting individual
employee privacy.

DESIGN CONTRACT — PRIVACY POSTURE
---------------------------------
This is the most privacy-sensitive engine in the Resource
Optimization arc. Hard rules:

1. **No individual names/codes ever appear in team-level
   outputs.** Team-level signals report counts, percentages,
   bands — never per-employee scores by name.
2. **Aggregate suppression** — any team-level cell with fewer
   than `MIN_TEAM_SIZE` (=5) employees is suppressed entirely
   (returns `data_suppressed=True`, no other fields). Prevents
   re-identification by elimination.
3. **No clinical claims.** Engine produces "risk band"
   classifications for operational use (HR triage,
   intervention prioritisation). Never "burnout diagnosis" or
   any term suggesting clinical assessment.
4. **Opt-out respected.** When the underlying #19 engine
   returns `{}` (employee opted out), this engine treats them
   as absent from the cohort — they don't reduce the n_total
   for suppression, they DON'T appear in counts. Test:
   `test_optout_excluded`.
5. **No automatic action.** Engine RECOMMENDS interventions
   (mandatory leave, workload redistribution, EAP referral) but
   never executes them. Caller / HR owns the decision.

WHAT THIS ENGINE PRODUCES
-------------------------
- `assess_team_signal(team_code, staff_codes)` — team-level
  burnout signal: counts in each risk band, sustained-breach
  flag if utilization data shows STRETCHED/BREACH for N days,
  recommended intervention level, all without naming
  individuals
- `multi_team_summary(...)` — same but rolled up across teams
  for HR_DIRECTOR scope (still no individual names)

REGULATORY BASIS
----------------
- Kenya Occupational Safety and Health Act 2007 §6 (employer
  duty to protect physical & mental health)
- DPA 2019 §44 (special category — health data — explicit
  consent / legitimate interest tests)
- Internal Mental Health & Wellbeing Policy
- Internal Hybrid Work Framework (workload-related stress
  monitoring)

HONEST DEFERRALS
----------------
- CLINICAL_VALIDATION: engine produces operational risk
  bands, NOT clinical diagnoses; no validated clinical
  instrument (MBI, Oldenburg, Copenhagen) integrated
- SENTIMENT_FEED_NLP: no NLP on emails/chat/Slack; explicitly
  out of scope at v10.185 (raises severe consent/§44 issues)
- EAP_INTEGRATION_PUSH: EAP referrals are output, never auto-
  pushed to provider — operator handles
- K_ANONYMITY_FORMAL: aggregate suppression is rule-based
  (n < 5 → suppress); no formal k-anonymity guarantee against
  background-knowledge attacks
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# Privacy threshold — team cells smaller than this are
# suppressed entirely. Aligns with ENH-156's threshold of 5.
MIN_TEAM_SIZE = 5


class TeamWellbeingBand(Enum):
    """Operational risk band for a team."""
    GREEN = "green"           # most members low-risk, no
                              # sustained utilization breach
    AMBER = "amber"           # some elevated risk OR pattern
                              # warning
    RED = "red"               # multiple high-risk members AND
                              # sustained utilization issues


class InterventionLevel(Enum):
    """Operator-actionable recommendation level."""
    MONITOR = "monitor"
    SOFT_INTERVENTION = "soft_intervention"
    # e.g. workload review at next 1-on-1
    HARD_INTERVENTION = "hard_intervention"
    # e.g. mandatory schedule rebalance + HR review
    EAP_REFERRAL = "eap_referral"
    # team-wide EAP communication; never per-individual auto


@dataclass(frozen=True)
class TeamSignal:
    """Team-level wellbeing signal — no individual names."""
    team_code: str
    n_total: int
    n_assessed: int
    n_optout: int
    band: TeamWellbeingBand
    risk_band_counts: Dict[str, int]
    # Counts of #19 risk_levels: Low / Moderate / High
    sustained_utilization_breach: bool
    intervention_level: InterventionLevel
    rationale: str
    data_suppressed: bool = False
    # When True, all other count fields are zero (suppression)
    assessed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_code": self.team_code,
            "n_total": self.n_total,
            "n_assessed": self.n_assessed,
            "n_optout": self.n_optout,
            "band": self.band.value,
            "risk_band_counts": dict(self.risk_band_counts),
            "sustained_utilization_breach": (
                self.sustained_utilization_breach),
            "intervention_level": self.intervention_level.value,
            "rationale": self.rationale,
            "data_suppressed": self.data_suppressed,
            "assessed_at": self.assessed_at.isoformat(),
        }


# Type alias for the wellness engine assessment function
# (matches WellnessEngine.assess_burnout_risk signature)
WellnessAssessor = Callable[[str], Dict[str, Any]]


class WellbeingIntegrationEngine:
    """Team-level early warning integration."""

    def __init__(
        self,
        wellness_assessor: WellnessAssessor,
        utilization_engine=None,
    ):
        """
        wellness_assessor: callable mapping staff_code → dict.
            Should match WellnessEngine.assess_burnout_risk
            output: {risk_level: 'Low'|'Moderate'|'High',
            risk_score: float, ...} or {} if opted out.
        utilization_engine: optional ENH-160 instance. When
            provided, sustained_utilization_breach is computed
            from team-level breach counts.
        """
        if wellness_assessor is None:
            raise ValueError("wellness_assessor required")
        self._assess = wellness_assessor
        self._util = utilization_engine
        self._signals: List[TeamSignal] = []

    # ─── core assessment ──────────────────────────────────────
    def assess_team_signal(
        self,
        team_code: str,
        staff_codes: List[str],
    ) -> TeamSignal:
        """Aggregate per-individual #19 assessments into a
        privacy-safe team signal."""
        if not team_code:
            raise ValueError("team_code required")
        n_total = len(staff_codes)

        # Suppression check — applied BEFORE running #19
        # assessments to avoid pointlessly accessing protected
        # data
        if n_total < MIN_TEAM_SIZE:
            return self._suppressed_signal(team_code, n_total)

        # Run per-employee assessment
        risk_counts = {"Low": 0, "Moderate": 0, "High": 0}
        n_optout = 0
        n_assessed = 0
        for code in staff_codes:
            result = self._assess(code) or {}
            if not result:
                # Opted out
                n_optout += 1
                continue
            level = result.get("risk_level")
            if level in risk_counts:
                risk_counts[level] += 1
                n_assessed += 1
            else:
                # Unknown risk_level — treat as not-assessed,
                # don't fabricate a category
                n_optout += 1

        # Apply suppression a second time on n_assessed
        # (consider that nearly all-opted-out also re-identifies)
        if n_assessed < MIN_TEAM_SIZE:
            return self._suppressed_signal(
                team_code, n_total, n_optout=n_optout)

        # Sustained utilization breach detection (if engine
        # available)
        sustained_breach = self._sustained_breach_for_team(
            team_code)

        # Band classification
        n_high = risk_counts["High"]
        n_moderate = risk_counts["Moderate"]
        pct_high_or_moderate = (
            (n_high + n_moderate) / n_assessed
            if n_assessed > 0 else 0.0)

        if n_high >= 3 and sustained_breach:
            band = TeamWellbeingBand.RED
            level = InterventionLevel.HARD_INTERVENTION
            rationale = (
                f"{n_high} high-risk individuals (≥3) with "
                f"sustained utilization breach pattern")
        elif n_high >= 3 or (
                pct_high_or_moderate >= 0.40
                and sustained_breach):
            band = TeamWellbeingBand.RED
            level = InterventionLevel.HARD_INTERVENTION
            rationale = (
                "Multiple high-risk indicators with elevated "
                "team workload pattern")
        elif n_high >= 1 or pct_high_or_moderate >= 0.30:
            band = TeamWellbeingBand.AMBER
            level = InterventionLevel.SOFT_INTERVENTION
            rationale = (
                "Elevated risk indicators present; manager "
                "wellbeing check recommended")
        elif sustained_breach:
            band = TeamWellbeingBand.AMBER
            level = InterventionLevel.SOFT_INTERVENTION
            rationale = (
                "No high-risk individuals but sustained "
                "utilization pressure; review workload")
        else:
            band = TeamWellbeingBand.GREEN
            level = InterventionLevel.MONITOR
            rationale = "No early warning signals detected"

        # If RED + many affected → EAP referral
        if (band == TeamWellbeingBand.RED
                and pct_high_or_moderate >= 0.50):
            level = InterventionLevel.EAP_REFERRAL
            rationale += "; team-wide EAP communication advised"

        signal = TeamSignal(
            team_code=team_code,
            n_total=n_total,
            n_assessed=n_assessed,
            n_optout=n_optout,
            band=band,
            risk_band_counts=risk_counts,
            sustained_utilization_breach=sustained_breach,
            intervention_level=level,
            rationale=rationale,
        )
        self._signals.append(signal)
        return signal

    # ─── helpers ──────────────────────────────────────────────
    def _suppressed_signal(
        self,
        team_code: str,
        n_total: int,
        n_optout: int = 0,
    ) -> TeamSignal:
        sig = TeamSignal(
            team_code=team_code,
            n_total=n_total,
            n_assessed=0,
            n_optout=n_optout,
            band=TeamWellbeingBand.GREEN,
            risk_band_counts={"Low": 0, "Moderate": 0, "High": 0},
            sustained_utilization_breach=False,
            intervention_level=InterventionLevel.MONITOR,
            rationale=(
                f"data suppressed — assessable cohort < "
                f"{MIN_TEAM_SIZE}"),
            data_suppressed=True,
        )
        self._signals.append(sig)
        return sig

    def _sustained_breach_for_team(
        self, team_code: str
    ) -> bool:
        """If utilization engine attached, check if team has
        any current BREACH-band channel. Conservative — sustained
        defined here as 'at least one current breach'; full
        rolling-window logic is deferred."""
        if self._util is None:
            return False
        try:
            breaches = self._util.list_breaches()
        except Exception:
            return False
        return any(
            getattr(s, "team_key", None) == team_code
            for s in breaches)

    # ─── multi-team rollup ────────────────────────────────────
    def multi_team_summary(
        self,
        teams: List[Tuple[str, List[str]]],
    ) -> Dict[str, Any]:
        """Aggregate signal across multiple teams.

        Input: list of (team_code, staff_codes) pairs.
        Output: bands distribution + intervention distribution +
        n_teams_suppressed.
        """
        signals = [
            self.assess_team_signal(tc, codes)
            for tc, codes in teams
        ]
        bands = {b.value: 0 for b in TeamWellbeingBand}
        levels = {lv.value: 0 for lv in InterventionLevel}
        n_suppressed = 0
        for s in signals:
            if s.data_suppressed:
                n_suppressed += 1
                continue
            bands[s.band.value] += 1
            levels[s.intervention_level.value] += 1
        return {
            "n_teams_total": len(signals),
            "n_teams_suppressed": n_suppressed,
            "n_teams_published": len(signals) - n_suppressed,
            "bands_distribution": bands,
            "intervention_distribution": levels,
        }

    # ─── queries ──────────────────────────────────────────────
    def list_signals(self) -> List[TeamSignal]:
        return list(self._signals)

    # ─── board ────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        bands = {b.value: 0 for b in TeamWellbeingBand}
        levels = {lv.value: 0 for lv in InterventionLevel}
        n_suppressed = 0
        for s in self._signals:
            if s.data_suppressed:
                n_suppressed += 1
                continue
            bands[s.band.value] += 1
            levels[s.intervention_level.value] += 1

        return {
            "engine": "ENH-161 WellbeingIntegrationEngine",
            "n_team_assessments_lifetime": len(self._signals),
            "n_team_assessments_suppressed": n_suppressed,
            "bands_distribution": bands,
            "intervention_distribution": levels,
            "min_team_size_for_publish": MIN_TEAM_SIZE,
            "utilization_engine_attached": self._util is not None,
            "regulatory_basis": (
                "Kenya OSH Act 2007 §6 + DPA 2019 §44 "
                "(special category) + Internal Mental Health & "
                "Wellbeing Policy"),
            "deferrals": {
                "CLINICAL_VALIDATION": (
                    "DEFERRED — operational risk bands only; "
                    "no validated clinical instrument (MBI, "
                    "Oldenburg, Copenhagen) integrated"),
                "SENTIMENT_FEED_NLP": (
                    "DEFERRED — explicitly out of scope; "
                    "raises severe consent/§44 issues if NLP on "
                    "emails/chat were added"),
                "EAP_INTEGRATION_PUSH": (
                    "DEFERRED — EAP referrals are output "
                    "recommendations only, never auto-pushed"),
                "K_ANONYMITY_FORMAL": (
                    "DEFERRED — aggregate suppression is rule-"
                    "based (n<5); no formal k-anonymity "
                    "guarantee against background-knowledge "
                    "attacks"),
            },
        }

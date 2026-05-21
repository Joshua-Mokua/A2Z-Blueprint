"""utils/credit_alt_scoring.py — v10.47: Alternative Credit Scoring.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-260 — Alternative Credit Scoring (Enhanced)                        ║
║  Cat A — credit_model_risk arc opens                                    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Distinct from utils.credit_risk_scoring (Standard #53 — bureau-based  ║
║  PD/LGD/EAD) and utils.credit_risk_irb (ENH-CR-001 — regulatory IRB     ║
║  capital). This module covers the THIN-FILE applicant case where        ║
║  bureau data is absent or insufficient: PD is estimated from three      ║
║  alternative pillars per CGAP + Smart Campaign + IFC Inclusive Finance: ║
║                                                                          ║
║    1. TRANSACTION pillar  — deposit regularity, salary-cycle signal,    ║
║                              bills-paid-on-time (via this bank),        ║
║                              expense/deposit ratio                      ║
║    2. BEHAVIORAL pillar    — tenure with bank, mobile-banking activity, ║
║                              current-facility delinquency days          ║
║    3. PSYCHOMETRIC pillar  — optional minimal questionnaire (risk       ║
║                              tolerance + time-preference horizon)       ║
║                                                                          ║
║  Each pillar produces a sub-PD AND a confidence weight (0 when missing).║
║  Composite alt_PD = weighted mean by confidence; overall confidence     ║
║  = sum(weights) / 3. Below CONFIDENCE_LOW_THRESHOLD the engine flags    ║
║  recommend_bureau_check=True so underwriting escalates rather than      ║
║  acting on a thin-file estimate.                                        ║
║                                                                          ║
║  Per Rule 1: every AltScoringResult surfaces                            ║
║    pillar_scores (per-pillar PD + confidence + features used)           ║
║    + composite_pd + confidence_band + grade + missing_pillars           ║
║    + recommend_bureau_check + framework_refs                            ║
║                                                                          ║
║  Per Rule 7: engine is computational only — never auto-approves a       ║
║  loan, never auto-declines, never updates the credit bureau. Output     ║
║  feeds underwriting workflow + credit committee discussion.             ║
║                                                                          ║
║  Pure stdlib (math + Decimal). No scipy.                                ║
║                                                                          ║
║  Composes with:                                                          ║
║    - credit_risk_scoring (Standard #53 baseline bureau scoring — when   ║
║      bureau data later becomes available, the alt score can be          ║
║      blended; not done here)                                            ║
║    - credit_risk_irb (ENH-CR-001 — alt-PD output can flow into IRB     ║
║      capital calculation via the same pd parameter)                     ║
║    - audit_grc (decision rationale capture — future composition)       ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Tuple

from utils.credit_risk_scoring import RISK_GRADES, PD_BANDS

SPEC_DEVIATION_NOTE = (
    "AlternativeCreditScoringEngine implements ENH-260 thin-file "
    "PD estimation. Pure stdlib via math + Decimal. Per Rule 1, "
    "every AltScoringResult surfaces all 3 pillar PDs + confidence "
    "weights + features used + composite + grade + framework refs. "
    "Per Rule 7, computational only — never auto-approves, never "
    "auto-declines, never writes to bureau. Confidence-weighted "
    "composite ensures a single strong pillar cannot dominate when "
    "other pillars are missing — the engine surfaces "
    "recommend_bureau_check=True below the confidence threshold "
    "rather than producing a brittle thin-file decision."
)

# ════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════

# Pillar weights when all three are fully populated (sum to 1.0)
PILLAR_WEIGHT_TRANSACTION = Decimal("0.50")
PILLAR_WEIGHT_BEHAVIORAL = Decimal("0.30")
PILLAR_WEIGHT_PSYCHOMETRIC = Decimal("0.20")

# Confidence threshold below which we recommend bureau escalation
CONFIDENCE_LOW_THRESHOLD = Decimal("0.40")
CONFIDENCE_MEDIUM_THRESHOLD = Decimal("0.70")

# PD bounds (consistent with Basel d424 IRB floor)
PD_FLOOR = 0.0003     # 3 bp floor matches IRB
PD_CEILING = 0.9999   # below 1.0 to allow IRB compatibility

# Minimum signal counts before a pillar is considered usable
MIN_TRANSACTION_MONTHS = 3
MIN_BEHAVIORAL_TENURE_MONTHS = 1


class ConfidenceBand(Enum):
    """Confidence classification of the alt-PD estimate."""
    HIGH = "HIGH"        # all 3 pillars contributing
    MEDIUM = "MEDIUM"    # 2 pillars contributing
    LOW = "LOW"          # 0-1 pillars contributing → escalate


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TransactionMetrics:
    """Transaction-pillar inputs aggregated over the observation window."""
    months_observed: int
    monthly_deposit_cv: Optional[float]   # coefficient of variation
    salary_cycle_signal: Optional[bool]   # True if recurring deposit pattern
    expense_to_deposit_ratio: Optional[float]
    bills_on_time_pct: Optional[float]    # in [0, 1]

    def __post_init__(self) -> None:
        if self.months_observed < 0:
            raise ValueError("months_observed must be ≥ 0")
        if (self.bills_on_time_pct is not None
                and not (0.0 <= self.bills_on_time_pct <= 1.0)):
            raise ValueError(
                f"bills_on_time_pct={self.bills_on_time_pct} "
                f"outside [0, 1]")
        if (self.expense_to_deposit_ratio is not None
                and self.expense_to_deposit_ratio < 0):
            raise ValueError(
                "expense_to_deposit_ratio must be ≥ 0")


@dataclass(frozen=True)
class BehavioralMetrics:
    """Behavioral-pillar inputs."""
    tenure_months: int
    mobile_active_days_per_month: Optional[float]
    current_facility_delinquency_days: Optional[int]

    def __post_init__(self) -> None:
        if self.tenure_months < 0:
            raise ValueError("tenure_months must be ≥ 0")
        if (self.current_facility_delinquency_days is not None
                and self.current_facility_delinquency_days < 0):
            raise ValueError(
                "current_facility_delinquency_days must be ≥ 0")
        if (self.mobile_active_days_per_month is not None
                and not (0.0 <= self.mobile_active_days_per_month <= 31.0)):
            raise ValueError(
                f"mobile_active_days_per_month="
                f"{self.mobile_active_days_per_month} outside [0, 31]")


@dataclass(frozen=True)
class PsychometricMetrics:
    """Psychometric-pillar inputs (optional minimal questionnaire)."""
    risk_tolerance_score: Optional[float]   # in [0, 1], higher = riskier
    time_horizon_score: Optional[float]     # in [0, 1], higher = longer-term

    def __post_init__(self) -> None:
        for name, val in (
            ("risk_tolerance_score", self.risk_tolerance_score),
            ("time_horizon_score", self.time_horizon_score),
        ):
            if val is not None and not (0.0 <= val <= 1.0):
                raise ValueError(f"{name}={val} outside [0, 1]")


@dataclass(frozen=True)
class ThinFileApplicant:
    """Aggregate input for one alt-scoring computation."""
    applicant_id: str
    transaction: Optional[TransactionMetrics] = None
    behavioral: Optional[BehavioralMetrics] = None
    psychometric: Optional[PsychometricMetrics] = None
    notes: str = ""


@dataclass(frozen=True)
class PillarScore:
    """Per-pillar output for full Rule 1 surfacing."""
    pillar_name: str
    pillar_pd: Optional[float]   # None when pillar unusable
    confidence_weight: Decimal   # 0..1
    features_used: Tuple[str, ...]
    skip_reason: str = ""        # populated when pillar unusable


@dataclass(frozen=True)
class AltScoringResult:
    """Output of an alt-scoring computation."""
    applicant_id: str
    pillar_scores: Tuple[PillarScore, ...]
    composite_pd: Optional[float]   # None when no pillar usable
    grade: Optional[str]            # S&P-style, None when composite_pd None
    confidence_band: ConfidenceBand
    overall_confidence: Decimal
    missing_pillars: Tuple[str, ...]
    recommend_bureau_check: bool
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class AlternativeCreditScoringEngine:
    """Thin-file PD engine.

    Per Rule 7, computational only. The engine never:
      - auto-approves or auto-declines a loan
      - writes to the credit bureau
      - mutates applicant records
    """

    # ── Pillar 1: TRANSACTION ─────────────────────────────────────────
    def _score_transaction(
        self, m: Optional[TransactionMetrics],
    ) -> PillarScore:
        if m is None or m.months_observed < MIN_TRANSACTION_MONTHS:
            return PillarScore(
                pillar_name="TRANSACTION",
                pillar_pd=None,
                confidence_weight=Decimal("0"),
                features_used=(),
                skip_reason=(
                    "no transaction data" if m is None
                    else f"only {m.months_observed} months observed; "
                         f"need ≥ {MIN_TRANSACTION_MONTHS}"))

        used: List[str] = ["months_observed"]
        # Each sub-signal is normalised to a [0, 1] PD-contribution band
        # where higher = riskier. Then we average the available
        # sub-signals and convert to a PD via a logistic-style bound.
        signals: List[float] = []

        # Deposit volatility — high CV ≈ irregular cash flow ≈ riskier
        if m.monthly_deposit_cv is not None:
            used.append("monthly_deposit_cv")
            # CV in [0, 1] → contribution in [0, 0.6]; CV > 1 caps
            signals.append(min(m.monthly_deposit_cv, 1.0) * 0.6)

        # Salary-cycle signal — present = lower risk
        if m.salary_cycle_signal is not None:
            used.append("salary_cycle_signal")
            signals.append(0.10 if m.salary_cycle_signal else 0.50)

        # Expense-to-deposit ratio — high ratio ≈ thin liquidity
        if m.expense_to_deposit_ratio is not None:
            used.append("expense_to_deposit_ratio")
            r = m.expense_to_deposit_ratio
            # ratio < 0.7 → low contribution, ratio > 1.0 → max
            signals.append(min(max((r - 0.5) / 0.7, 0.0), 1.0) * 0.55)

        # Bills on time — strong inverse signal
        if m.bills_on_time_pct is not None:
            used.append("bills_on_time_pct")
            signals.append((1.0 - m.bills_on_time_pct) * 0.65)

        if not signals:
            return PillarScore(
                pillar_name="TRANSACTION",
                pillar_pd=None,
                confidence_weight=Decimal("0"),
                features_used=tuple(used),
                skip_reason="months observed but no sub-signals supplied")

        # Average sub-signals, map to PD via a smooth function.
        # Floor / ceiling bound the result.
        avg = sum(signals) / len(signals)
        pd = self._signal_to_pd(avg)

        # Confidence weight scales with both data depth (months) and
        # signal coverage (how many sub-signals supplied out of 4).
        depth = min(m.months_observed / 12.0, 1.0)
        coverage = len(signals) / 4.0
        cw = Decimal(str(round(depth * coverage, 4)))

        return PillarScore(
            pillar_name="TRANSACTION",
            pillar_pd=pd,
            confidence_weight=cw,
            features_used=tuple(used))

    # ── Pillar 2: BEHAVIORAL ──────────────────────────────────────────
    def _score_behavioral(
        self, m: Optional[BehavioralMetrics],
    ) -> PillarScore:
        if (m is None
                or m.tenure_months < MIN_BEHAVIORAL_TENURE_MONTHS):
            return PillarScore(
                pillar_name="BEHAVIORAL",
                pillar_pd=None,
                confidence_weight=Decimal("0"),
                features_used=(),
                skip_reason=(
                    "no behavioral data" if m is None
                    else f"tenure {m.tenure_months}m below "
                         f"{MIN_BEHAVIORAL_TENURE_MONTHS}m minimum"))

        used: List[str] = ["tenure_months"]
        signals: List[float] = []

        # Tenure — longer relationship ≈ lower risk
        # 0-3m → 0.50, 6m → 0.35, 12m → 0.20, 24m+ → 0.10
        tenure_signal = max(0.10, 0.55 - 0.02 * m.tenure_months)
        signals.append(min(tenure_signal, 0.55))

        if m.mobile_active_days_per_month is not None:
            used.append("mobile_active_days_per_month")
            # Active engagement reduces estimated risk
            d = m.mobile_active_days_per_month
            mob_sig = max(0.05, 0.45 - 0.013 * d)  # 30 days → ~0.06
            signals.append(min(mob_sig, 0.50))

        if m.current_facility_delinquency_days is not None:
            used.append("current_facility_delinquency_days")
            d = m.current_facility_delinquency_days
            # Delinquency is the strongest single behavioral signal
            if d == 0:
                signals.append(0.10)
            elif d < 30:
                signals.append(0.45)
            elif d < 60:
                signals.append(0.70)
            elif d < 90:
                signals.append(0.85)
            else:
                signals.append(0.95)

        avg = sum(signals) / len(signals)
        pd = self._signal_to_pd(avg)

        # Confidence: tenure depth (cap 24m) × signal coverage (3 max)
        depth = min(m.tenure_months / 24.0, 1.0)
        coverage = len(signals) / 3.0
        cw = Decimal(str(round(depth * coverage, 4)))

        return PillarScore(
            pillar_name="BEHAVIORAL",
            pillar_pd=pd,
            confidence_weight=cw,
            features_used=tuple(used))

    # ── Pillar 3: PSYCHOMETRIC ────────────────────────────────────────
    def _score_psychometric(
        self, m: Optional[PsychometricMetrics],
    ) -> PillarScore:
        if (m is None
                or (m.risk_tolerance_score is None
                    and m.time_horizon_score is None)):
            return PillarScore(
                pillar_name="PSYCHOMETRIC",
                pillar_pd=None,
                confidence_weight=Decimal("0"),
                features_used=(),
                skip_reason=(
                    "no psychometric data" if m is None
                    else "questionnaire incomplete"))

        used: List[str] = []
        signals: List[float] = []

        # Risk tolerance — high tolerance ≈ higher risk-taking ≈ riskier
        if m.risk_tolerance_score is not None:
            used.append("risk_tolerance_score")
            signals.append(m.risk_tolerance_score * 0.55)

        # Time horizon — longer-term thinking = lower risk
        if m.time_horizon_score is not None:
            used.append("time_horizon_score")
            signals.append((1.0 - m.time_horizon_score) * 0.45)

        avg = sum(signals) / len(signals)
        pd = self._signal_to_pd(avg)

        # Psychometric confidence is inherently capped — treat 2/2 as
        # full coverage; 1/2 as half.
        coverage = len(signals) / 2.0
        cw = Decimal(str(round(coverage * 0.7, 4)))

        return PillarScore(
            pillar_name="PSYCHOMETRIC",
            pillar_pd=pd,
            confidence_weight=cw,
            features_used=tuple(used))

    # ── Helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _signal_to_pd(signal: float) -> float:
        """Map an aggregated signal in [0, 1] to a PD via a smooth
        function. Boundaries: signal 0 → ~PD_FLOOR; signal 1 → ~0.50.

        Uses a power transform tuned so a 'typical' signal of ~0.30
        yields PD ~ 0.04 (≈ Basel BB grade), keeping the engine in
        a calibrated range for thin-file applicants.
        """
        # Clip
        s = max(0.0, min(signal, 1.0))
        # Power transform — exponent 1.8 spreads low signals
        pd = 0.50 * (s ** 1.8)
        # Floor / ceiling
        return max(PD_FLOOR, min(pd, PD_CEILING))

    def _pd_to_grade(self, pd: float) -> str:
        """Map PD to S&P-style grade by upper-bound lookup."""
        for grade in RISK_GRADES:
            if pd <= PD_BANDS[grade]:
                return grade
        return RISK_GRADES[-1]

    def _composite(
        self, scores: Tuple[PillarScore, ...],
    ) -> Tuple[Optional[float], Decimal, ConfidenceBand]:
        """Combine pillar scores into composite PD + confidence."""
        # Default pillar weights — only counted when pillar is usable.
        weights = {
            "TRANSACTION": PILLAR_WEIGHT_TRANSACTION,
            "BEHAVIORAL": PILLAR_WEIGHT_BEHAVIORAL,
            "PSYCHOMETRIC": PILLAR_WEIGHT_PSYCHOMETRIC,
        }

        usable = [s for s in scores if s.pillar_pd is not None]
        if not usable:
            return (None, Decimal("0"), ConfidenceBand.LOW)

        # Effective weight of each usable pillar = base weight ×
        # confidence_weight. Renormalise across usable pillars.
        eff = {
            s.pillar_name: weights[s.pillar_name] * s.confidence_weight
            for s in usable}
        total_eff = sum(eff.values(), Decimal("0"))
        if total_eff <= 0:
            return (None, Decimal("0"), ConfidenceBand.LOW)
        norm_weights = {
            name: w / total_eff for name, w in eff.items()}

        composite = sum(
            float(norm_weights[s.pillar_name]) * s.pillar_pd
            for s in usable)
        composite = max(PD_FLOOR, min(composite, PD_CEILING))

        # Overall confidence = mean of (base_weight × conf_weight)
        # across all 3 pillar slots — penalises missing pillars.
        overall = sum(
            (weights[name] * (
                next((s.confidence_weight for s in scores
                      if s.pillar_name == name), Decimal("0"))))
            for name in weights)
        overall = (overall / sum(weights.values())).quantize(
            Decimal("0.0001"))

        # Band
        if overall >= CONFIDENCE_MEDIUM_THRESHOLD:
            band = ConfidenceBand.HIGH
        elif overall >= CONFIDENCE_LOW_THRESHOLD:
            band = ConfidenceBand.MEDIUM
        else:
            band = ConfidenceBand.LOW

        return (composite, overall, band)

    # ── Public API ────────────────────────────────────────────────────
    def compute(self, applicant: ThinFileApplicant) -> AltScoringResult:
        """Score one thin-file applicant."""
        scores = (
            self._score_transaction(applicant.transaction),
            self._score_behavioral(applicant.behavioral),
            self._score_psychometric(applicant.psychometric),
        )
        composite, overall, band = self._composite(scores)
        missing = tuple(
            s.pillar_name for s in scores if s.pillar_pd is None)
        grade = self._pd_to_grade(composite) if composite else None
        recommend_bureau = (
            band == ConfidenceBand.LOW or composite is None)
        return AltScoringResult(
            applicant_id=applicant.applicant_id,
            pillar_scores=scores,
            composite_pd=composite,
            grade=grade,
            confidence_band=band,
            overall_confidence=overall,
            missing_pillars=missing,
            recommend_bureau_check=recommend_bureau,
            framework_refs=(
                "CGAP Thin-File Lending Guidance",
                "Smart Campaign Client Protection Principles",
                "IFC Inclusive Finance — Alternative Data",
                "CBK PG/03 Credit Risk Management",
            ),
            notes=applicant.notes)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_transaction_validates_bills_pct_in_range():
    try:
        TransactionMetrics(
            months_observed=6, monthly_deposit_cv=0.2,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.7,
            bills_on_time_pct=1.5)
        assert False
    except ValueError:
        pass


def _test_behavioral_validates_delinquency_non_negative():
    try:
        BehavioralMetrics(
            tenure_months=12,
            mobile_active_days_per_month=20,
            current_facility_delinquency_days=-1)
        assert False
    except ValueError:
        pass


def _test_psychometric_validates_risk_score_in_range():
    try:
        PsychometricMetrics(
            risk_tolerance_score=2.0, time_horizon_score=0.5)
        assert False
    except ValueError:
        pass


def _test_no_pillars_returns_low_confidence():
    eng = AlternativeCreditScoringEngine()
    r = eng.compute(ThinFileApplicant(applicant_id="empty"))
    assert r.composite_pd is None
    assert r.confidence_band == ConfidenceBand.LOW
    assert r.recommend_bureau_check is True
    assert len(r.missing_pillars) == 3


def _test_short_tenure_skips_behavioral_pillar():
    eng = AlternativeCreditScoringEngine()
    r = eng.compute(ThinFileApplicant(
        applicant_id="newbie",
        behavioral=BehavioralMetrics(
            tenure_months=0, mobile_active_days_per_month=10,
            current_facility_delinquency_days=0)))
    behavioral = next(
        s for s in r.pillar_scores if s.pillar_name == "BEHAVIORAL")
    assert behavioral.pillar_pd is None
    assert "tenure" in behavioral.skip_reason


def _test_short_transaction_window_skips_pillar():
    eng = AlternativeCreditScoringEngine()
    r = eng.compute(ThinFileApplicant(
        applicant_id="thin_txn",
        transaction=TransactionMetrics(
            months_observed=1, monthly_deposit_cv=0.1,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.5,
            bills_on_time_pct=1.0)))
    txn = next(
        s for s in r.pillar_scores if s.pillar_name == "TRANSACTION")
    assert txn.pillar_pd is None
    assert "months" in txn.skip_reason


def _test_healthy_thin_file_low_pd_high_confidence():
    """Strong signals across all 3 pillars → low PD, HIGH band."""
    eng = AlternativeCreditScoringEngine()
    applicant = ThinFileApplicant(
        applicant_id="healthy",
        transaction=TransactionMetrics(
            months_observed=12,
            monthly_deposit_cv=0.10,         # very stable
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.55,
            bills_on_time_pct=0.95),
        behavioral=BehavioralMetrics(
            tenure_months=24,
            mobile_active_days_per_month=22,
            current_facility_delinquency_days=0),
        psychometric=PsychometricMetrics(
            risk_tolerance_score=0.30,
            time_horizon_score=0.80))
    r = eng.compute(applicant)
    assert r.composite_pd is not None
    assert r.composite_pd < 0.05, (
        f"healthy thin-file PD={r.composite_pd} should be < 5%")
    assert r.confidence_band == ConfidenceBand.HIGH
    assert r.recommend_bureau_check is False


def _test_risky_thin_file_high_pd():
    """Weak/negative signals → high PD."""
    eng = AlternativeCreditScoringEngine()
    applicant = ThinFileApplicant(
        applicant_id="risky",
        transaction=TransactionMetrics(
            months_observed=6,
            monthly_deposit_cv=0.90,       # very irregular
            salary_cycle_signal=False,
            expense_to_deposit_ratio=1.05,
            bills_on_time_pct=0.40),
        behavioral=BehavioralMetrics(
            tenure_months=4,
            mobile_active_days_per_month=3,
            current_facility_delinquency_days=45))
    r = eng.compute(applicant)
    assert r.composite_pd is not None
    assert r.composite_pd > 0.10, (
        f"risky thin-file PD={r.composite_pd} should be > 10%")


def _test_pd_floor_enforced():
    """Even all-perfect inputs cannot produce PD below floor."""
    eng = AlternativeCreditScoringEngine()
    applicant = ThinFileApplicant(
        applicant_id="impossible_perfect",
        transaction=TransactionMetrics(
            months_observed=24,
            monthly_deposit_cv=0.0,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.0,
            bills_on_time_pct=1.0),
        behavioral=BehavioralMetrics(
            tenure_months=60,
            mobile_active_days_per_month=30,
            current_facility_delinquency_days=0),
        psychometric=PsychometricMetrics(
            risk_tolerance_score=0.0,
            time_horizon_score=1.0))
    r = eng.compute(applicant)
    assert r.composite_pd is not None
    assert r.composite_pd >= PD_FLOOR


def _test_grade_assigned_from_pd():
    eng = AlternativeCreditScoringEngine()
    # Force a moderate PD via balanced inputs
    applicant = ThinFileApplicant(
        applicant_id="grade_test",
        transaction=TransactionMetrics(
            months_observed=12, monthly_deposit_cv=0.30,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.70,
            bills_on_time_pct=0.85),
        behavioral=BehavioralMetrics(
            tenure_months=18,
            mobile_active_days_per_month=15,
            current_facility_delinquency_days=0))
    r = eng.compute(applicant)
    assert r.grade in RISK_GRADES


def _test_one_pillar_only_yields_medium_or_low_band():
    eng = AlternativeCreditScoringEngine()
    r = eng.compute(ThinFileApplicant(
        applicant_id="one_pillar",
        transaction=TransactionMetrics(
            months_observed=12, monthly_deposit_cv=0.20,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.60,
            bills_on_time_pct=0.90)))
    assert r.confidence_band in (
        ConfidenceBand.MEDIUM, ConfidenceBand.LOW)


def _test_recommend_bureau_when_confidence_low():
    eng = AlternativeCreditScoringEngine()
    # Provide weak psychometric only (low pillar weight)
    r = eng.compute(ThinFileApplicant(
        applicant_id="weak_only",
        psychometric=PsychometricMetrics(
            risk_tolerance_score=0.5, time_horizon_score=None)))
    assert r.confidence_band == ConfidenceBand.LOW
    assert r.recommend_bureau_check is True


def _test_pillar_score_surfaces_features_used():
    """Per Rule 1 — each pillar reports which features it consumed."""
    eng = AlternativeCreditScoringEngine()
    r = eng.compute(ThinFileApplicant(
        applicant_id="features_test",
        transaction=TransactionMetrics(
            months_observed=6, monthly_deposit_cv=0.2,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=None,
            bills_on_time_pct=0.85)))
    txn = next(
        s for s in r.pillar_scores if s.pillar_name == "TRANSACTION")
    assert "monthly_deposit_cv" in txn.features_used
    assert "salary_cycle_signal" in txn.features_used
    assert "bills_on_time_pct" in txn.features_used
    assert "expense_to_deposit_ratio" not in txn.features_used


def _test_result_has_full_provenance():
    """Per Rule 1 — result surfaces grade + missing + framework refs."""
    eng = AlternativeCreditScoringEngine()
    r = eng.compute(ThinFileApplicant(
        applicant_id="prov",
        transaction=TransactionMetrics(
            months_observed=6, monthly_deposit_cv=0.2,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.7,
            bills_on_time_pct=0.9)))
    assert len(r.pillar_scores) == 3
    assert len(r.framework_refs) >= 3
    assert any(
        "CGAP" in ref or "Smart Campaign" in ref
        for ref in r.framework_refs)
    assert "BEHAVIORAL" in r.missing_pillars
    assert "PSYCHOMETRIC" in r.missing_pillars


def _test_signal_to_pd_monotonic():
    """Higher signal → higher PD (within bounds)."""
    eng = AlternativeCreditScoringEngine()
    pd_low = eng._signal_to_pd(0.10)
    pd_mid = eng._signal_to_pd(0.50)
    pd_high = eng._signal_to_pd(0.90)
    assert pd_low < pd_mid < pd_high


def self_test() -> None:
    tests = [
        _test_transaction_validates_bills_pct_in_range,
        _test_behavioral_validates_delinquency_non_negative,
        _test_psychometric_validates_risk_score_in_range,
        _test_no_pillars_returns_low_confidence,
        _test_short_tenure_skips_behavioral_pillar,
        _test_short_transaction_window_skips_pillar,
        _test_healthy_thin_file_low_pd_high_confidence,
        _test_risky_thin_file_high_pd,
        _test_pd_floor_enforced,
        _test_grade_assigned_from_pd,
        _test_one_pillar_only_yields_medium_or_low_band,
        _test_recommend_bureau_when_confidence_low,
        _test_pillar_score_surfaces_features_used,
        _test_result_has_full_provenance,
        _test_signal_to_pd_monotonic,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ credit_alt_scoring self-test: {len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ credit_alt_scoring self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

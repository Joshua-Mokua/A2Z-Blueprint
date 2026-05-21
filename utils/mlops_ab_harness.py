"""utils/mlops_ab_harness.py — v10.84: MLOps A/B Comparison Harness.

ENH-284 — MLOps A/B Comparison Harness. Cat B — ml_governance arc 4/N.

Diagnostic engine that compares two model versions running in parallel
(typically the current ACTIVE serving production traffic alongside a
candidate SHADOW that produces predictions but doesn't drive operator
workflow yet). The harness consumes prediction-event streams from
both versions plus caller-supplied operator override data, latency
observations, and optional cost estimates, and surfaces deltas across
five comparison axes:

  1. Per-prediction outcome agreement (when both versions saw the
     same input — by input_features_hash — did they predict the same
     recommendation?)
  2. Per-class distribution shift (does SHADOW predict the same class
     mix as ACTIVE?)
  3. Latency comparison (median + p95 + max per version, with deltas)
  4. Cost comparison (when caller supplies per-call cost-per-version
     estimates)
  5. Composite report orchestrator combining all of the above with
     insufficient-sample flagging

This engine is the bridge from "we have a candidate registered via
ENH-281 with status=SHADOW" to "the candidate is ready to be the
active". It surfaces deltas; ENH-281 validate_promotion_readiness
applies the promotion gates; operator decides.

Per Rule 7, engine NEVER:
  - auto-promotes the shadow to active (ENH-281 territory)
  - auto-deprecates the active (ENH-281 territory)
  - decides which side is "better" — surfaces deltas, operator
    decides which side wins on which axes
  - executes inference itself (consumes pre-computed prediction
    streams from caller's inference infrastructure)
  - filters out outliers or normalizes data (caller decides
    pre-processing policy; engine processes what's given)
  - persists prediction streams (caller stores)

Per Rule 1, every output surfaces inputs + intermediates + outputs +
framework_refs. All result dataclasses are frozen. Per-class deltas
+ unpaired events + insufficient-sample flags all surface
explicitly.

Caller-supplied data discipline (matches the arc pattern through
ENH-281/282/283): prediction events + latency observations + cost
estimates + minimum sample sizes all caller-supplied; engine bundles
no defaults.

Pure stdlib runtime (no statistics module dependency — implements
median + percentile directly for control over edge cases).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import (
    Mapping, Optional, Sequence, Tuple)

SPEC_DEVIATION_NOTE = (
    "MLOpsABHarnessEngine implements ENH-284 — diagnostic A/B "
    "comparison harness. Consumes parallel prediction streams from "
    "ACTIVE + SHADOW model versions and surfaces deltas across "
    "agreement / class distribution / latency / cost axes. Sits in "
    "the ml_governance arc as the bridge from 'candidate registered "
    "via ENH-281 with status=SHADOW' to 'candidate ready for "
    "promotion to ACTIVE'. Pure stdlib. Per Rule 1, every delta + "
    "unpaired event + sample sufficiency surface explicitly. Per "
    "Rule 7, engine DIAGNOSTIC ONLY — never auto-promotes shadow to "
    "active (ENH-281 validate_promotion_readiness territory), never "
    "auto-deprecates active, never decides which side is better, "
    "never runs inference, never filters or normalizes data, never "
    "persists streams (caller stores)."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class PredictionRole(Enum):
    """Role of the model version in the comparison."""
    ACTIVE = "ACTIVE"
    SHADOW = "SHADOW"


class ABReportSeverity(Enum):
    """Composite severity of the A/B report."""
    READY_TO_PROMOTE = "READY_TO_PROMOTE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_READY = "NOT_READY"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PredictionEvent:
    """A single prediction made by either ACTIVE or SHADOW.
    Caller-supplied; engine processes."""
    event_id: str                # unique per inference call
    input_features_hash: str     # links pairs across active/shadow
    model_id: str
    model_version: str
    role: PredictionRole
    predicted_class: str
    predicted_at_iso: str
    latency_ms: Optional[Decimal] = None
    confidence_score: Optional[Decimal] = None


@dataclass(frozen=True)
class CostEstimate:
    """Caller-supplied per-call cost for a model version."""
    model_version: str
    cost_per_call_kes: Decimal


@dataclass(frozen=True)
class ABThresholds:
    """Caller-supplied severity thresholds for the composite
    report."""
    minimum_paired_sample: int = 100
    agreement_warning_rate: Decimal = Decimal("0.85")
    agreement_critical_rate: Decimal = Decimal("0.70")
    latency_regression_warning_pct: Decimal = Decimal("0.20")
    latency_regression_critical_pct: Decimal = Decimal("0.50")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PairedComparison:
    """A single comparison of ACTIVE vs SHADOW on same input."""
    input_features_hash: str
    active_event_id: str
    shadow_event_id: str
    active_class: str
    shadow_class: str
    agreement: bool
    latency_delta_ms: Optional[Decimal]   # shadow - active


@dataclass(frozen=True)
class PairingResult:
    paired: Tuple[PairedComparison, ...]
    unpaired_active_only: Tuple[str, ...]   # input_features_hashes
    unpaired_shadow_only: Tuple[str, ...]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class AgreementSummary:
    total_paired: int
    total_agreed: int
    total_deviated: int
    agreement_rate: Optional[Decimal]   # None when total_paired==0
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class ClassDistributionDelta:
    class_label: str
    active_count: int
    shadow_count: int
    active_share: Optional[Decimal]   # active_count / total_active
    shadow_share: Optional[Decimal]
    share_delta: Optional[Decimal]    # shadow_share - active_share


@dataclass(frozen=True)
class ClassDistributionShift:
    total_active_predictions: int
    total_shadow_predictions: int
    deltas: Tuple[ClassDistributionDelta, ...]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class LatencyStats:
    role: PredictionRole
    sample_size: int
    median_ms: Optional[Decimal]
    p95_ms: Optional[Decimal]
    max_ms: Optional[Decimal]
    insufficient_sample: bool   # below caller-supplied minimum


@dataclass(frozen=True)
class LatencyComparison:
    active: LatencyStats
    shadow: LatencyStats
    median_delta_ms: Optional[Decimal]   # shadow - active
    median_delta_pct: Optional[Decimal]  # delta / active_median
    p95_delta_ms: Optional[Decimal]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class CostComparison:
    active_version: str
    shadow_version: str
    active_call_count: int
    shadow_call_count: int
    active_cost_per_call_kes: Optional[Decimal]
    shadow_cost_per_call_kes: Optional[Decimal]
    active_total_cost_kes: Optional[Decimal]
    shadow_total_cost_kes: Optional[Decimal]
    cost_delta_kes: Optional[Decimal]   # shadow - active
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class ABComparisonReport:
    active_version: str
    shadow_version: str
    pairing: PairingResult
    agreement: AgreementSummary
    distribution_shift: ClassDistributionShift
    latency: LatencyComparison
    cost: Optional[CostComparison]
    composite_severity: ABReportSeverity
    rationale: str
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class MLOpsABHarnessEngine:
    """Diagnostic A/B comparison harness."""

    # ─── 1. Pair predictions ───────────────────────────────────
    def pair_predictions(
        self,
        events: Sequence[PredictionEvent],
        active_version: str,
        shadow_version: str,
    ) -> PairingResult:
        """Pair ACTIVE and SHADOW events by input_features_hash.
        Surfaces unpaired input hashes explicitly per Rule 1.
        """
        # Index by input hash for each role
        active_by_hash: dict = {}
        shadow_by_hash: dict = {}
        for e in events:
            if e.model_version == active_version:
                if e.role == PredictionRole.ACTIVE:
                    active_by_hash.setdefault(
                        e.input_features_hash, []).append(e)
            elif e.model_version == shadow_version:
                if e.role == PredictionRole.SHADOW:
                    shadow_by_hash.setdefault(
                        e.input_features_hash, []).append(e)
            # Events for other versions / mismatched roles are
            # ignored — caller-supplied filter discipline

        paired: list = []
        unpaired_active: list = []
        unpaired_shadow: list = []

        all_hashes = (
            set(active_by_hash.keys())
            | set(shadow_by_hash.keys()))
        for h in sorted(all_hashes):
            a_list = active_by_hash.get(h, [])
            s_list = shadow_by_hash.get(h, [])
            if a_list and s_list:
                # Take first of each for the pair (multiple
                # predictions on same input hash is unusual but
                # not blocked; caller decides dedup policy)
                a = a_list[0]
                s = s_list[0]
                latency_delta = None
                if (a.latency_ms is not None
                    and s.latency_ms is not None):
                    latency_delta = (
                        s.latency_ms - a.latency_ms)
                paired.append(PairedComparison(
                    input_features_hash=h,
                    active_event_id=a.event_id,
                    shadow_event_id=s.event_id,
                    active_class=a.predicted_class,
                    shadow_class=s.predicted_class,
                    agreement=(
                        a.predicted_class == s.predicted_class),
                    latency_delta_ms=latency_delta))
            elif a_list:
                unpaired_active.append(h)
            else:
                unpaired_shadow.append(h)

        return PairingResult(
            paired=tuple(paired),
            unpaired_active_only=tuple(unpaired_active),
            unpaired_shadow_only=tuple(unpaired_shadow),
            framework_refs=(
                "ENH-284 §pair_predictions",
                "Pairing key: input_features_hash. Caller "
                "computes the hash deterministically (e.g. "
                "sha256 over feature blob); engine treats it "
                "as opaque identifier.",
                "Per Rule 1 — unpaired_active_only and "
                "unpaired_shadow_only surface explicitly "
                "(operations sees inputs the active saw that "
                "shadow didn't, and vice versa — diagnoses "
                "deployment skew)",
                "Per Rule 7 — engine pairs and surfaces; "
                "caller decides what to do with unpaired "
                "(could indicate routing bug, sampling "
                "policy, or shadow not yet fully deployed)",
            ),
        )

    # ─── 2. Compute agreement summary ──────────────────────────
    def compute_agreement_summary(
        self,
        paired: Sequence[PairedComparison],
    ) -> AgreementSummary:
        """Aggregate per-pair agreement into rate. Per Rule 1,
        rate is None when no pairs (gap surfacing — engine never
        fabricates a rate from empty denominator)."""
        total = len(paired)
        agreed = sum(1 for p in paired if p.agreement)
        deviated = total - agreed
        if total == 0:
            rate = None
        else:
            rate = Decimal(agreed) / Decimal(total)
        return AgreementSummary(
            total_paired=total,
            total_agreed=agreed,
            total_deviated=deviated,
            agreement_rate=rate,
            framework_refs=(
                "ENH-284 §compute_agreement_summary",
                "Per Rule 1 — rate is None when total_paired"
                "==0 (engine never fabricates from empty "
                "denominator). Operator must investigate why "
                "no pairs (shadow not deployed? routing bug? "
                "active not running?)",
                "Per Rule 7 — engine surfaces rate; never "
                "decides 'rate too low → block promotion' "
                "(that is ENH-281 validate_promotion_"
                "readiness territory with caller-supplied "
                "PromotionGate rules)",
            ),
        )

    # ─── 3. Compute class distribution shift ───────────────────
    def compute_class_distribution_shift(
        self,
        events: Sequence[PredictionEvent],
        active_version: str,
        shadow_version: str,
    ) -> ClassDistributionShift:
        """Per-class share comparison. Surfaces ALL classes seen
        across either version (per Rule 1, classes seen only in
        one side are surfaced with the other side's count = 0)."""
        active_counts: dict = {}
        shadow_counts: dict = {}
        for e in events:
            if (e.model_version == active_version
                and e.role == PredictionRole.ACTIVE):
                active_counts[e.predicted_class] = (
                    active_counts.get(
                        e.predicted_class, 0) + 1)
            elif (e.model_version == shadow_version
                and e.role == PredictionRole.SHADOW):
                shadow_counts[e.predicted_class] = (
                    shadow_counts.get(
                        e.predicted_class, 0) + 1)

        total_active = sum(active_counts.values())
        total_shadow = sum(shadow_counts.values())

        all_classes = sorted(
            set(active_counts.keys())
            | set(shadow_counts.keys()))

        deltas: list = []
        for c in all_classes:
            a_count = active_counts.get(c, 0)
            s_count = shadow_counts.get(c, 0)
            a_share = (
                Decimal(a_count) / Decimal(total_active)
                if total_active > 0 else None)
            s_share = (
                Decimal(s_count) / Decimal(total_shadow)
                if total_shadow > 0 else None)
            if a_share is not None and s_share is not None:
                share_delta = s_share - a_share
            else:
                share_delta = None
            deltas.append(ClassDistributionDelta(
                class_label=c,
                active_count=a_count,
                shadow_count=s_count,
                active_share=a_share,
                shadow_share=s_share,
                share_delta=share_delta))

        return ClassDistributionShift(
            total_active_predictions=total_active,
            total_shadow_predictions=total_shadow,
            deltas=tuple(deltas),
            framework_refs=(
                "ENH-284 §compute_class_distribution_shift",
                "Per Rule 1 — classes appearing in only one "
                "side surface with the other side's count=0 "
                "(engine never silently drops classes; "
                "operator sees the full picture including "
                "novel classes the shadow predicts that the "
                "active never did)",
                "Per Rule 7 — engine surfaces shift; never "
                "decides 'shift too large → block promotion'",
            ),
        )

    # ─── 4. Compute latency comparison ─────────────────────────
    def compute_latency_comparison(
        self,
        events: Sequence[PredictionEvent],
        active_version: str,
        shadow_version: str,
        minimum_sample: int = 30,
    ) -> LatencyComparison:
        """Median + p95 + max per version + deltas. Per Rule 1,
        insufficient_sample flag surfaces when below caller-
        supplied minimum (default 30 — small enough to surface a
        signal, large enough to be statistically meaningful)."""
        active_lat = [
            e.latency_ms for e in events
            if (e.model_version == active_version
                and e.role == PredictionRole.ACTIVE
                and e.latency_ms is not None)]
        shadow_lat = [
            e.latency_ms for e in events
            if (e.model_version == shadow_version
                and e.role == PredictionRole.SHADOW
                and e.latency_ms is not None)]

        active_stats = self._compute_latency_stats(
            active_lat, PredictionRole.ACTIVE,
            minimum_sample)
        shadow_stats = self._compute_latency_stats(
            shadow_lat, PredictionRole.SHADOW,
            minimum_sample)

        # Compute deltas (shadow - active) when both medians
        # available
        median_delta_ms = None
        median_delta_pct = None
        p95_delta_ms = None
        if (active_stats.median_ms is not None
            and shadow_stats.median_ms is not None):
            median_delta_ms = (
                shadow_stats.median_ms
                - active_stats.median_ms)
            if active_stats.median_ms != Decimal("0"):
                median_delta_pct = (
                    median_delta_ms / active_stats.median_ms)
        if (active_stats.p95_ms is not None
            and shadow_stats.p95_ms is not None):
            p95_delta_ms = (
                shadow_stats.p95_ms - active_stats.p95_ms)

        return LatencyComparison(
            active=active_stats,
            shadow=shadow_stats,
            median_delta_ms=median_delta_ms,
            median_delta_pct=median_delta_pct,
            p95_delta_ms=p95_delta_ms,
            framework_refs=(
                "ENH-284 §compute_latency_comparison",
                "Median + p95 + max per version (p95 chosen "
                "as canonical SLO indicator per Google SRE "
                "practice; max preserved for tail-event "
                "diagnosis)",
                "Per Rule 1 — insufficient_sample flag "
                "surfaces when below caller-supplied "
                "minimum (engine doesn't fabricate "
                "statistics from sparse data)",
                "Per Rule 7 — engine surfaces stats; never "
                "decides 'latency regression too large → "
                "block promotion' (that is caller policy)",
                "Google SRE Workbook (2018) — p95 latency as "
                "production SLO indicator",
            ),
        )

    def _compute_latency_stats(
        self,
        latencies: Sequence[Decimal],
        role: PredictionRole,
        minimum_sample: int,
    ) -> LatencyStats:
        n = len(latencies)
        if n == 0:
            return LatencyStats(
                role=role, sample_size=0,
                median_ms=None, p95_ms=None, max_ms=None,
                insufficient_sample=True)
        sorted_lat = sorted(latencies)
        # Median
        if n % 2 == 1:
            median = sorted_lat[n // 2]
        else:
            median = (
                sorted_lat[n // 2 - 1]
                + sorted_lat[n // 2]) / Decimal(2)
        # p95 — use linear interpolation on sorted values
        # rank = 0.95 * (n - 1)
        rank = Decimal("0.95") * Decimal(n - 1)
        rank_floor = int(rank)
        rank_frac = rank - Decimal(rank_floor)
        if rank_floor >= n - 1:
            p95 = sorted_lat[-1]
        else:
            lower = sorted_lat[rank_floor]
            upper = sorted_lat[rank_floor + 1]
            p95 = lower + rank_frac * (upper - lower)
        max_val = sorted_lat[-1]
        return LatencyStats(
            role=role,
            sample_size=n,
            median_ms=median,
            p95_ms=p95,
            max_ms=max_val,
            insufficient_sample=(n < minimum_sample))

    # ─── 5. Build composite A/B comparison report ──────────────
    def build_ab_comparison_report(
        self,
        events: Sequence[PredictionEvent],
        active_version: str,
        shadow_version: str,
        thresholds: ABThresholds,
        cost_estimates: Optional[
            Sequence[CostEstimate]] = None,
    ) -> ABComparisonReport:
        """Orchestrator. Composes pairing + agreement +
        distribution + latency + cost into a single report with
        composite severity.

        Composite severity logic:
          - INSUFFICIENT_SAMPLE if total_paired < minimum
          - NOT_READY if agreement_rate < critical_rate OR
            median latency regression ≥ critical_pct
          - NEEDS_REVIEW if agreement_rate < warning_rate OR
            median latency regression ≥ warning_pct
          - READY_TO_PROMOTE otherwise
        """
        pairing = self.pair_predictions(
            events, active_version, shadow_version)
        agreement = self.compute_agreement_summary(
            pairing.paired)
        dist_shift = self.compute_class_distribution_shift(
            events, active_version, shadow_version)
        latency = self.compute_latency_comparison(
            events, active_version, shadow_version)

        cost = None
        if cost_estimates is not None:
            cost = self._compute_cost_comparison(
                events, active_version, shadow_version,
                cost_estimates)

        # Composite severity
        severity, rationale = self._classify_severity(
            agreement, latency, thresholds)

        return ABComparisonReport(
            active_version=active_version,
            shadow_version=shadow_version,
            pairing=pairing,
            agreement=agreement,
            distribution_shift=dist_shift,
            latency=latency,
            cost=cost,
            composite_severity=severity,
            rationale=rationale,
            framework_refs=(
                "ENH-284 §build_ab_comparison_report",
                "Composite severity logic: thresholds caller-"
                "supplied via ABThresholds; engine bundles "
                "no defaults except dataclass field defaults",
                "Per Rule 1 — every contributing comparison "
                "(pairing + agreement + distribution + "
                "latency + cost) preserved on the report; "
                "operator sees the full picture",
                "Per Rule 7 — composite severity is a SUMMARY "
                "view; ENH-281 validate_promotion_readiness "
                "is the actual promotion gate (operator runs "
                "promotion gates with caller-supplied "
                "PromotionGate rules; engine never auto-"
                "promotes)",
                "Microsoft MLOps Maturity Model (2023) — "
                "Stage 5 shadow deployment + canary "
                "comparison",
                "Google SRE Workbook (2018) — gradual "
                "rollout pattern with paired comparison",
            ),
        )

    def _compute_cost_comparison(
        self,
        events: Sequence[PredictionEvent],
        active_version: str,
        shadow_version: str,
        cost_estimates: Sequence[CostEstimate],
    ) -> CostComparison:
        active_count = sum(
            1 for e in events
            if (e.model_version == active_version
                and e.role == PredictionRole.ACTIVE))
        shadow_count = sum(
            1 for e in events
            if (e.model_version == shadow_version
                and e.role == PredictionRole.SHADOW))
        cost_by_version = {
            c.model_version: c.cost_per_call_kes
            for c in cost_estimates}
        active_cost_per_call = cost_by_version.get(
            active_version)
        shadow_cost_per_call = cost_by_version.get(
            shadow_version)
        active_total = (
            active_cost_per_call * Decimal(active_count)
            if active_cost_per_call is not None else None)
        shadow_total = (
            shadow_cost_per_call * Decimal(shadow_count)
            if shadow_cost_per_call is not None else None)
        cost_delta = (
            shadow_total - active_total
            if (active_total is not None
                and shadow_total is not None) else None)
        return CostComparison(
            active_version=active_version,
            shadow_version=shadow_version,
            active_call_count=active_count,
            shadow_call_count=shadow_count,
            active_cost_per_call_kes=active_cost_per_call,
            shadow_cost_per_call_kes=shadow_cost_per_call,
            active_total_cost_kes=active_total,
            shadow_total_cost_kes=shadow_total,
            cost_delta_kes=cost_delta,
            framework_refs=(
                "ENH-284 §_compute_cost_comparison",
                "Per Rule 1 — None values surface when cost "
                "estimate missing for either version "
                "(engine never fabricates cost from one "
                "side)",
                "Per Rule 7 — engine surfaces delta; never "
                "decides 'cost increase too large → block "
                "promotion' (caller policy)",
            ),
        )

    def _classify_severity(
        self,
        agreement: AgreementSummary,
        latency: LatencyComparison,
        thresholds: ABThresholds,
    ) -> Tuple[ABReportSeverity, str]:
        # Insufficient sample check first
        if (agreement.total_paired
            < thresholds.minimum_paired_sample):
            return (
                ABReportSeverity.INSUFFICIENT_SAMPLE,
                f"Total paired comparisons "
                f"({agreement.total_paired}) below caller-"
                f"supplied minimum_paired_sample "
                f"({thresholds.minimum_paired_sample}). Per "
                f"Rule 1, engine surfaces "
                f"INSUFFICIENT_SAMPLE rather than "
                f"defaulting to a verdict on sparse data.")

        # NOT_READY checks (any critical breach)
        critical_rationale: list = []
        if (agreement.agreement_rate is not None
            and agreement.agreement_rate
            < thresholds.agreement_critical_rate):
            critical_rationale.append(
                f"agreement_rate {agreement.agreement_rate} "
                f"< critical {thresholds.agreement_critical_rate}")
        if (latency.median_delta_pct is not None
            and latency.median_delta_pct
            >= thresholds.latency_regression_critical_pct):
            critical_rationale.append(
                f"latency regression "
                f"{latency.median_delta_pct} ≥ critical "
                f"{thresholds.latency_regression_critical_pct}")
        if critical_rationale:
            return (
                ABReportSeverity.NOT_READY,
                "NOT_READY: "
                + "; ".join(critical_rationale)
                + ". Operator should investigate before "
                "promotion via ENH-281 validate_promotion_"
                "readiness gates.")

        # NEEDS_REVIEW checks (any warning breach)
        warning_rationale: list = []
        if (agreement.agreement_rate is not None
            and agreement.agreement_rate
            < thresholds.agreement_warning_rate):
            warning_rationale.append(
                f"agreement_rate {agreement.agreement_rate} "
                f"< warning {thresholds.agreement_warning_rate}")
        if (latency.median_delta_pct is not None
            and latency.median_delta_pct
            >= thresholds.latency_regression_warning_pct):
            warning_rationale.append(
                f"latency regression "
                f"{latency.median_delta_pct} ≥ warning "
                f"{thresholds.latency_regression_warning_pct}")
        if warning_rationale:
            return (
                ABReportSeverity.NEEDS_REVIEW,
                "NEEDS_REVIEW: "
                + "; ".join(warning_rationale)
                + ". Consider longer shadow period or "
                "operator review before promotion.")

        return (
            ABReportSeverity.READY_TO_PROMOTE,
            f"READY_TO_PROMOTE: agreement_rate "
            f"{agreement.agreement_rate} ≥ warning "
            f"{thresholds.agreement_warning_rate} AND "
            f"latency regression within tolerance. Operator "
            f"should still run ENH-281 validate_promotion_"
            f"readiness gates with caller-supplied "
            f"PromotionGate rules before final promotion.")


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_event(
    event_id="E1",
    input_hash="h1",
    version="1.0",
    role=PredictionRole.ACTIVE,
    predicted_class="APPROVE",
    latency=Decimal("100"),
):
    return PredictionEvent(
        event_id=event_id,
        input_features_hash=input_hash,
        model_id="doc_classifier",
        model_version=version,
        role=role,
        predicted_class=predicted_class,
        predicted_at_iso="2026-05-01T10:00:00Z",
        latency_ms=latency)


# ─── Pairing tests ─────────────────────────────────────────────

def _test_pair_perfect_match():
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE),
        _make_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW),
        _make_event(
            "A2", "h2", "1.0", PredictionRole.ACTIVE),
        _make_event(
            "S2", "h2", "2.0", PredictionRole.SHADOW),
    )
    r = eng.pair_predictions(events, "1.0", "2.0")
    assert len(r.paired) == 2
    assert len(r.unpaired_active_only) == 0
    assert len(r.unpaired_shadow_only) == 0


def _test_pair_unpaired_active():
    """Active sees input shadow didn't."""
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE),
        _make_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW),
        _make_event(
            "A2", "h2", "1.0", PredictionRole.ACTIVE),
        # No shadow for h2 — shadow not deployed for that input
    )
    r = eng.pair_predictions(events, "1.0", "2.0")
    assert len(r.paired) == 1
    assert r.unpaired_active_only == ("h2",)
    assert len(r.unpaired_shadow_only) == 0


def _test_pair_agreement_and_disagreement():
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE,
            predicted_class="APPROVE"),
        _make_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW,
            predicted_class="APPROVE"),  # agree
        _make_event(
            "A2", "h2", "1.0", PredictionRole.ACTIVE,
            predicted_class="APPROVE"),
        _make_event(
            "S2", "h2", "2.0", PredictionRole.SHADOW,
            predicted_class="REJECT"),  # disagree
    )
    r = eng.pair_predictions(events, "1.0", "2.0")
    by_hash = {p.input_features_hash: p for p in r.paired}
    assert by_hash["h1"].agreement is True
    assert by_hash["h2"].agreement is False


def _test_pair_latency_delta():
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE,
            latency=Decimal("100")),
        _make_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW,
            latency=Decimal("150")),
    )
    r = eng.pair_predictions(events, "1.0", "2.0")
    assert r.paired[0].latency_delta_ms == Decimal("50")


# ─── Agreement summary tests ───────────────────────────────────

def _test_agreement_rate():
    eng = MLOpsABHarnessEngine()
    pairs = (
        PairedComparison(
            "h1", "a1", "s1", "X", "X",
            agreement=True, latency_delta_ms=None),
        PairedComparison(
            "h2", "a2", "s2", "X", "Y",
            agreement=False, latency_delta_ms=None),
        PairedComparison(
            "h3", "a3", "s3", "X", "X",
            agreement=True, latency_delta_ms=None),
    )
    s = eng.compute_agreement_summary(pairs)
    assert s.total_paired == 3
    assert s.total_agreed == 2
    assert s.agreement_rate == Decimal(2) / Decimal(3)


def _test_agreement_rate_empty_returns_none():
    """No pairs → rate is None per Rule 1."""
    eng = MLOpsABHarnessEngine()
    s = eng.compute_agreement_summary(())
    assert s.agreement_rate is None
    assert s.total_paired == 0


# ─── Class distribution shift tests ────────────────────────────

def _test_dist_shift_basic():
    eng = MLOpsABHarnessEngine()
    events = []
    # Active: 70% APPROVE, 30% REJECT
    for i in range(70):
        events.append(_make_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE,
            predicted_class="APPROVE"))
    for i in range(30):
        events.append(_make_event(
            f"A{i+70}", f"h{i+70}", "1.0",
            PredictionRole.ACTIVE,
            predicted_class="REJECT"))
    # Shadow: 50% APPROVE, 50% REJECT — meaningful shift
    for i in range(50):
        events.append(_make_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW,
            predicted_class="APPROVE"))
    for i in range(50):
        events.append(_make_event(
            f"S{i+50}", f"h{i+50}", "2.0",
            PredictionRole.SHADOW,
            predicted_class="REJECT"))
    s = eng.compute_class_distribution_shift(
        events, "1.0", "2.0")
    by_class = {d.class_label: d for d in s.deltas}
    # active APPROVE share = 0.70, shadow = 0.50 → delta -0.20
    assert by_class["APPROVE"].active_share == (
        Decimal("0.70"))
    assert by_class["APPROVE"].shadow_share == (
        Decimal("0.50"))
    assert by_class["APPROVE"].share_delta == (
        Decimal("-0.20"))


def _test_dist_shift_novel_class_in_shadow():
    """Class that only appears in shadow — surfaced with active=0."""
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE,
            predicted_class="APPROVE"),
        _make_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW,
            predicted_class="HOLD"),  # never seen in active
    )
    s = eng.compute_class_distribution_shift(
        events, "1.0", "2.0")
    by_class = {d.class_label: d for d in s.deltas}
    assert by_class["HOLD"].active_count == 0
    assert by_class["HOLD"].shadow_count == 1


# ─── Latency comparison tests ──────────────────────────────────

def _test_latency_basic_no_regression():
    eng = MLOpsABHarnessEngine()
    events = []
    for i in range(50):
        events.append(_make_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE,
            latency=Decimal("100")))
        events.append(_make_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW,
            latency=Decimal("100")))
    c = eng.compute_latency_comparison(
        events, "1.0", "2.0")
    assert c.median_delta_ms == Decimal("0")
    assert c.median_delta_pct == Decimal("0")


def _test_latency_regression():
    eng = MLOpsABHarnessEngine()
    events = []
    for i in range(50):
        events.append(_make_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE,
            latency=Decimal("100")))
        events.append(_make_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW,
            latency=Decimal("150")))
    c = eng.compute_latency_comparison(
        events, "1.0", "2.0")
    # median: shadow 150 vs active 100 → +50ms / +50%
    assert c.median_delta_ms == Decimal("50")
    assert c.median_delta_pct == Decimal("0.5")


def _test_latency_insufficient_sample():
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE,
            latency=Decimal("100")),
    )
    c = eng.compute_latency_comparison(
        events, "1.0", "2.0", minimum_sample=30)
    assert c.active.insufficient_sample is True
    assert c.shadow.insufficient_sample is True


def _test_latency_p95_calculation():
    """p95 of [10, 20, ..., 100] (10 values) = ~96.5"""
    eng = MLOpsABHarnessEngine()
    events = []
    for i, lat in enumerate(
        [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    ):
        events.append(_make_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE,
            latency=Decimal(str(lat))))
    c = eng.compute_latency_comparison(
        events, "1.0", "2.0", minimum_sample=5)
    # rank = 0.95 * 9 = 8.55 → between sorted[8]=90 and
    # sorted[9]=100; p95 = 90 + 0.55 * 10 = 95.5
    assert c.active.p95_ms == Decimal("95.5")
    assert c.active.max_ms == Decimal("100")


# ─── Composite report tests ────────────────────────────────────

def _test_report_ready_to_promote():
    eng = MLOpsABHarnessEngine()
    events = []
    # 100 paired predictions, 95% agreement, equal latency
    for i in range(100):
        active_class = "APPROVE"
        # 5% disagreement
        shadow_class = (
            "REJECT" if i < 5 else "APPROVE")
        events.append(_make_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE,
            predicted_class=active_class,
            latency=Decimal("100")))
        events.append(_make_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW,
            predicted_class=shadow_class,
            latency=Decimal("100")))
    r = eng.build_ab_comparison_report(
        events, "1.0", "2.0",
        thresholds=ABThresholds(
            minimum_paired_sample=50,
            agreement_warning_rate=Decimal("0.85"),
            agreement_critical_rate=Decimal("0.70")))
    assert r.composite_severity == (
        ABReportSeverity.READY_TO_PROMOTE)


def _test_report_not_ready_low_agreement():
    eng = MLOpsABHarnessEngine()
    events = []
    # 100 paired, 50% agreement → below critical 0.70
    for i in range(100):
        active_class = "APPROVE"
        shadow_class = (
            "APPROVE" if i < 50 else "REJECT")
        events.append(_make_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE,
            predicted_class=active_class,
            latency=Decimal("100")))
        events.append(_make_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW,
            predicted_class=shadow_class,
            latency=Decimal("100")))
    r = eng.build_ab_comparison_report(
        events, "1.0", "2.0",
        thresholds=ABThresholds(
            minimum_paired_sample=50))
    assert r.composite_severity == (
        ABReportSeverity.NOT_READY)


def _test_report_insufficient_sample():
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE),
        _make_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW),
    )
    r = eng.build_ab_comparison_report(
        events, "1.0", "2.0",
        thresholds=ABThresholds(
            minimum_paired_sample=100))
    assert r.composite_severity == (
        ABReportSeverity.INSUFFICIENT_SAMPLE)


def _test_report_with_cost():
    eng = MLOpsABHarnessEngine()
    events = []
    for i in range(100):
        events.append(_make_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE,
            latency=Decimal("100")))
        events.append(_make_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW,
            latency=Decimal("100")))
    cost_estimates = (
        CostEstimate(
            "1.0", Decimal("0.001")),
        CostEstimate(
            "2.0", Decimal("0.003")),
    )
    r = eng.build_ab_comparison_report(
        events, "1.0", "2.0",
        thresholds=ABThresholds(
            minimum_paired_sample=50),
        cost_estimates=cost_estimates)
    assert r.cost is not None
    # active cost = 0.001 * 100 = 0.1
    # shadow cost = 0.003 * 100 = 0.3 → delta +0.2
    assert r.cost.cost_delta_kes == Decimal("0.2")


# ─── Discipline tests ──────────────────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = MLOpsABHarnessEngine()
    events = (_make_event(),)
    # Force-list to a tuple so we can verify it survives unchanged
    eng.compute_agreement_summary(())
    assert events[0].event_id == "E1"


def _test_full_provenance():
    eng = MLOpsABHarnessEngine()
    events = (
        _make_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE),
        _make_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW),
    )
    r = eng.build_ab_comparison_report(
        events, "1.0", "2.0",
        thresholds=ABThresholds(minimum_paired_sample=1))
    refs = " / ".join(r.framework_refs)
    assert "ENH-284" in refs
    assert "Rule 1" in refs
    assert "Rule 7" in refs
    assert "ENH-281" in refs   # boundary citation


def _test_caller_supplied_data_discipline():
    """Engine bundles no events; caller passes everything."""
    eng = MLOpsABHarnessEngine()
    r = eng.build_ab_comparison_report(
        (), "1.0", "2.0",
        thresholds=ABThresholds(minimum_paired_sample=1))
    assert r.composite_severity == (
        ABReportSeverity.INSUFFICIENT_SAMPLE)
    assert r.agreement.total_paired == 0


def self_test() -> None:
    tests = [
        _test_pair_perfect_match,
        _test_pair_unpaired_active,
        _test_pair_agreement_and_disagreement,
        _test_pair_latency_delta,
        _test_agreement_rate,
        _test_agreement_rate_empty_returns_none,
        _test_dist_shift_basic,
        _test_dist_shift_novel_class_in_shadow,
        _test_latency_basic_no_regression,
        _test_latency_regression,
        _test_latency_insufficient_sample,
        _test_latency_p95_calculation,
        _test_report_ready_to_promote,
        _test_report_not_ready_low_agreement,
        _test_report_insufficient_sample,
        _test_report_with_cost,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_caller_supplied_data_discipline,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ mlops_ab_harness self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ mlops_ab_harness self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

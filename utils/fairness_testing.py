"""utils/fairness_testing.py — v10.14 Phase 2 deep impl batch 8 (Credit batch 4 part 2).

╔════════════════════════════════════════════════════════════════════════╗
║  FAIRNESS TESTING — DISPARATE IMPACT + LDA-BASED LATENT BIAS SEARCH    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (regulatory compliance — discriminatory outcomes)   ║
║  Implements 1 of 19 Credit standards from registry:                     ║
║    ENH-CRD-R1: LDA-Based Bias Search & Disparate Impact Testing         ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    ECOA (Equal Credit Opportunity Act) — 15 USC §1691 et seq.          ║
║    Reg B 12 CFR Pt 1002 — implementing rules                            ║
║    Fair Housing Act (FHA) for mortgage lending                         ║
║    EEOC Uniform Guidelines on Employee Selection Procedures —           ║
║      4/5ths rule (29 CFR §1607.4(D)) is the disparate-impact analog    ║
║    EU AI Act Art 10 — fairness in training data                        ║
║    EU AI Act Art 15 — accuracy and non-discrimination                  ║
║    Kenya Constitution Art 27 — equality and freedom from discrimination║
║    Kenya Banking Act §52 — fair treatment of customers                 ║
║    Council of Europe Convention 108+                                   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Methodology references:                                                ║
║    Feldman et al. (2015) "Certifying and removing disparate impact"    ║
║    Dwork et al. (2012) "Fairness through awareness"                    ║
║    Hardt et al. (2016) "Equality of opportunity in supervised learning"║
║    Blei et al. (2003) — Latent Dirichlet Allocation (topic modeling)   ║
║                                                                         ║
║  The 4/5ths rule: protected-class approval rate / reference approval   ║
║  rate < 0.80 = potential disparate impact (rebuttable presumption).    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Honesty Rule 1: groups with insufficient sample size produce explicit ║
║  INSUFFICIENT_DATA result, never silently assumed equal to reference.  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

# ════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════

# 4/5ths rule threshold (EEOC + ECOA convention)
FOUR_FIFTHS_THRESHOLD = Decimal("0.80")

# Statistical parity difference threshold (industry default)
SPD_THRESHOLD_ABS = Decimal("0.10")    # ±10pp

# Equal opportunity difference threshold
EOD_THRESHOLD_ABS = Decimal("0.10")    # ±10pp

# Minimum sample size per group for reliable comparison
MIN_GROUP_SAMPLE_SIZE = 30


class ProtectedAttribute(Enum):
    """Protected classes per ECOA §1691 + Reg B §1002.6.

    Lenders MAY collect these for fairness monitoring (and in mortgage
    contexts MUST per HMDA), but they cannot be used in decision-making.
    """
    RACE = "RACE"
    NATIONAL_ORIGIN = "NATIONAL_ORIGIN"
    GENDER = "GENDER"
    MARITAL_STATUS = "MARITAL_STATUS"
    AGE = "AGE"                       # 40+ protected per ADEA
    RELIGION = "RELIGION"
    DISABILITY = "DISABILITY"
    PUBLIC_ASSISTANCE_INCOME = "PUBLIC_ASSISTANCE_INCOME"


class FairnessVerdict(Enum):
    """Outcome of disparate impact test."""
    PASS = "PASS"                      # ratio ≥ threshold
    POTENTIAL_DISPARATE_IMPACT = "POTENTIAL_DISPARATE_IMPACT"   # ratio < threshold, rebuttable
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REFERENCE_GROUP_NO_APPROVALS = "REFERENCE_GROUP_NO_APPROVALS"


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class OutcomeRecord:
    """Single decision outcome with protected-class label.

    The protected-class label MUST NOT be used as a model feature.
    It is captured only for post-decision fairness monitoring.
    """
    application_id: str
    decision: str                    # "APPROVE" / "DECLINE" / "REFER"
    protected_attribute: ProtectedAttribute
    protected_value: str             # e.g. "FEMALE" or "AGE_40_PLUS"
    is_reference_group: bool          # True for the reference (largest/majority)
    actual_outcome: Optional[str] = None  # for EOD: TRUE_POSITIVE etc.
    application_features_text: str = ""    # for LDA topic search

    def __post_init__(self):
        if self.decision not in ("APPROVE", "DECLINE", "REFER"):
            raise ValueError(f"unknown decision: {self.decision}")


@dataclass(frozen=True)
class DisparateImpactResult:
    """Result of disparate impact test for one protected class vs reference."""
    protected_attribute: ProtectedAttribute
    protected_value: str
    n_protected: int
    n_reference: int
    approve_rate_protected: Optional[Decimal]
    approve_rate_reference: Optional[Decimal]
    disparate_impact_ratio: Optional[Decimal]    # protected / reference
    statistical_parity_difference: Optional[Decimal]   # protected - reference
    threshold: Decimal
    verdict: FairnessVerdict
    notes: str = ""


@dataclass(frozen=True)
class EqualOpportunityResult:
    """Equal-opportunity-difference (EOD) — true positive rate parity."""
    protected_attribute: ProtectedAttribute
    protected_value: str
    tpr_protected: Optional[Decimal]
    tpr_reference: Optional[Decimal]
    equal_opportunity_difference: Optional[Decimal]
    threshold_abs: Decimal
    verdict: FairnessVerdict
    notes: str = ""


@dataclass(frozen=True)
class FairnessReport:
    """Full fairness audit report across all protected attributes."""
    entity_name: str
    period_start: str
    period_end: str
    n_total_applications: int
    disparate_impact_results: Tuple[DisparateImpactResult, ...]
    equal_opportunity_results: Tuple[EqualOpportunityResult, ...]
    overall_verdict: FairnessVerdict
    notes: str = ""

    def has_violations(self) -> bool:
        """True if any test returned POTENTIAL_DISPARATE_IMPACT."""
        for r in self.disparate_impact_results:
            if r.verdict == FairnessVerdict.POTENTIAL_DISPARATE_IMPACT:
                return True
        for r in self.equal_opportunity_results:
            if r.verdict == FairnessVerdict.POTENTIAL_DISPARATE_IMPACT:
                return True
        return False


# ════════════════════════════════════════════════════════════════════════
# Disparate Impact (4/5ths rule)
# ════════════════════════════════════════════════════════════════════════

def compute_disparate_impact_ratio(
    *,
    protected_records: Sequence[OutcomeRecord],
    reference_records: Sequence[OutcomeRecord],
    threshold: Decimal = FOUR_FIFTHS_THRESHOLD,
    min_sample_size: int = MIN_GROUP_SAMPLE_SIZE,
) -> DisparateImpactResult:
    """Compute the 4/5ths rule disparate impact ratio.

    DIR = approve_rate(protected) / approve_rate(reference)

    DIR < 0.80 = potential disparate impact (rebuttable).
    """
    n_p = len(protected_records)
    n_r = len(reference_records)

    if n_p < min_sample_size or n_r < min_sample_size:
        return DisparateImpactResult(
            protected_attribute=(
                protected_records[0].protected_attribute
                if protected_records else ProtectedAttribute.RACE),
            protected_value=(
                protected_records[0].protected_value
                if protected_records else "UNKNOWN"),
            n_protected=n_p, n_reference=n_r,
            approve_rate_protected=None,
            approve_rate_reference=None,
            disparate_impact_ratio=None,
            statistical_parity_difference=None,
            threshold=threshold,
            verdict=FairnessVerdict.INSUFFICIENT_DATA,
            notes=(
                f"insufficient sample: protected={n_p}, reference={n_r}; "
                f"need ≥ {min_sample_size} each"))

    approves_p = sum(1 for r in protected_records if r.decision == "APPROVE")
    approves_r = sum(1 for r in reference_records if r.decision == "APPROVE")

    rate_p = Decimal(approves_p) / Decimal(n_p)
    rate_r = Decimal(approves_r) / Decimal(n_r)

    if rate_r == Decimal("0"):
        return DisparateImpactResult(
            protected_attribute=protected_records[0].protected_attribute,
            protected_value=protected_records[0].protected_value,
            n_protected=n_p, n_reference=n_r,
            approve_rate_protected=rate_p,
            approve_rate_reference=rate_r,
            disparate_impact_ratio=None,
            statistical_parity_difference=rate_p - rate_r,
            threshold=threshold,
            verdict=FairnessVerdict.REFERENCE_GROUP_NO_APPROVALS,
            notes="reference group has zero approvals — DIR undefined")

    dir_ratio = rate_p / rate_r
    spd = rate_p - rate_r

    verdict = (
        FairnessVerdict.PASS if dir_ratio >= threshold
        else FairnessVerdict.POTENTIAL_DISPARATE_IMPACT)

    return DisparateImpactResult(
        protected_attribute=protected_records[0].protected_attribute,
        protected_value=protected_records[0].protected_value,
        n_protected=n_p, n_reference=n_r,
        approve_rate_protected=rate_p,
        approve_rate_reference=rate_r,
        disparate_impact_ratio=dir_ratio,
        statistical_parity_difference=spd,
        threshold=threshold,
        verdict=verdict,
        notes=(
            f"4/5ths rule: DIR={dir_ratio:.3f} vs threshold={threshold}; "
            f"approves: protected={approves_p}/{n_p}, "
            f"reference={approves_r}/{n_r}"))


# ════════════════════════════════════════════════════════════════════════
# Equal Opportunity Difference (EOD)
# ════════════════════════════════════════════════════════════════════════

def compute_equal_opportunity_difference(
    *,
    protected_records: Sequence[OutcomeRecord],
    reference_records: Sequence[OutcomeRecord],
    threshold_abs: Decimal = EOD_THRESHOLD_ABS,
    min_sample_size: int = MIN_GROUP_SAMPLE_SIZE,
) -> EqualOpportunityResult:
    """Equal Opportunity Difference: TPR_protected - TPR_reference.

    TPR (True Positive Rate) = approves among truly creditworthy applicants.
    Requires `actual_outcome` field populated ("CREDITWORTHY" / "NOT_CREDITWORTHY"
    based on subsequent loan performance).
    """
    # Filter to records with actual_outcome
    pr_with_outcome = [
        r for r in protected_records
        if r.actual_outcome == "CREDITWORTHY"]
    rf_with_outcome = [
        r for r in reference_records
        if r.actual_outcome == "CREDITWORTHY"]

    if (len(pr_with_outcome) < min_sample_size
            or len(rf_with_outcome) < min_sample_size):
        return EqualOpportunityResult(
            protected_attribute=(
                protected_records[0].protected_attribute
                if protected_records else ProtectedAttribute.RACE),
            protected_value=(
                protected_records[0].protected_value
                if protected_records else "UNKNOWN"),
            tpr_protected=None, tpr_reference=None,
            equal_opportunity_difference=None,
            threshold_abs=threshold_abs,
            verdict=FairnessVerdict.INSUFFICIENT_DATA,
            notes=(
                f"insufficient creditworthy outcomes: "
                f"protected={len(pr_with_outcome)}, "
                f"reference={len(rf_with_outcome)}"))

    approves_p = sum(1 for r in pr_with_outcome if r.decision == "APPROVE")
    approves_r = sum(1 for r in rf_with_outcome if r.decision == "APPROVE")

    tpr_p = Decimal(approves_p) / Decimal(len(pr_with_outcome))
    tpr_r = Decimal(approves_r) / Decimal(len(rf_with_outcome))

    eod = tpr_p - tpr_r

    if abs(eod) > threshold_abs:
        verdict = FairnessVerdict.POTENTIAL_DISPARATE_IMPACT
    else:
        verdict = FairnessVerdict.PASS

    return EqualOpportunityResult(
        protected_attribute=protected_records[0].protected_attribute,
        protected_value=protected_records[0].protected_value,
        tpr_protected=tpr_p, tpr_reference=tpr_r,
        equal_opportunity_difference=eod,
        threshold_abs=threshold_abs,
        verdict=verdict,
        notes=(
            f"TPR_protected={tpr_p:.3f}, TPR_reference={tpr_r:.3f}, "
            f"EOD={eod:.3f}"))


# ════════════════════════════════════════════════════════════════════════
# LDA-based latent bias search (simplified)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LatentTopicResult:
    """A latent topic identified in application text + its approval skew."""
    topic_id: str
    keywords: Tuple[str, ...]
    n_applications: int
    approval_rate: Decimal
    overall_approval_rate: Decimal
    approval_rate_delta: Decimal     # topic - overall
    is_potentially_biased: bool
    notes: str = ""


def lda_latent_bias_search(
    records: Sequence[OutcomeRecord],
    *,
    n_topics: int = 5,
    bias_delta_threshold: Decimal = Decimal("0.15"),
    min_topic_size: int = 20,
    keyword_extractor=None,
) -> Tuple[LatentTopicResult, ...]:
    """Simplified LDA-style latent bias search.

    Real LDA requires a sklearn/gensim pipeline + vocabulary + iterations.
    This rule-based simplification clusters applications by keyword overlap
    and surfaces topics whose approval rate diverges from the overall rate
    by more than `bias_delta_threshold`.

    Pass `keyword_extractor=callable(text) → frozenset(str)` to plug a
    proper LDA implementation (Rule 7 — LLM/ML hookable, no silent ML).
    """
    if not records:
        return ()

    # Default extractor: take alphanumeric tokens length ≥ 4, lowered
    if keyword_extractor is None:
        def keyword_extractor(text: str) -> frozenset:
            tokens = (
                "".join(c if c.isalnum() else " " for c in text)
                .lower().split())
            return frozenset(t for t in tokens if len(t) >= 4)

    # Build per-record keyword sets
    keyword_sets = [
        keyword_extractor(r.application_features_text) for r in records]

    # Find top-N most frequent keywords across the corpus
    keyword_freq: Dict[str, int] = {}
    for kws in keyword_sets:
        for kw in kws:
            keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

    top_keywords = sorted(
        keyword_freq.items(), key=lambda x: x[1], reverse=True)[:n_topics * 3]

    # Group records by their dominant top-keyword (simplified topic assignment)
    topics: Dict[str, List[int]] = {}      # keyword → record indices
    for i, kws in enumerate(keyword_sets):
        for kw, _freq in top_keywords[:n_topics]:
            if kw in kws:
                topics.setdefault(kw, []).append(i)
                break  # assign to first matching keyword

    # Overall approval rate
    overall_approves = sum(1 for r in records if r.decision == "APPROVE")
    overall_rate = Decimal(overall_approves) / Decimal(len(records))

    results: List[LatentTopicResult] = []
    for kw, indices in topics.items():
        if len(indices) < min_topic_size:
            continue
        topic_approves = sum(
            1 for i in indices if records[i].decision == "APPROVE")
        topic_rate = Decimal(topic_approves) / Decimal(len(indices))
        delta = topic_rate - overall_rate
        is_biased = abs(delta) > bias_delta_threshold

        results.append(LatentTopicResult(
            topic_id=f"TOPIC_{kw}",
            keywords=(kw,),
            n_applications=len(indices),
            approval_rate=topic_rate,
            overall_approval_rate=overall_rate,
            approval_rate_delta=delta,
            is_potentially_biased=is_biased,
            notes=(
                f"approves: {topic_approves}/{len(indices)} = "
                f"{topic_rate:.3f}; delta={delta:+.3f}")))

    # Sort by absolute delta (most-skewed topics first)
    results.sort(
        key=lambda r: abs(r.approval_rate_delta), reverse=True)
    return tuple(results)


# ════════════════════════════════════════════════════════════════════════
# Fairness report orchestrator
# ════════════════════════════════════════════════════════════════════════

def generate_fairness_report(
    *,
    entity_name: str,
    period_start: str,
    period_end: str,
    records: Sequence[OutcomeRecord],
) -> FairnessReport:
    """Run all fairness tests across all protected attributes."""
    di_results: List[DisparateImpactResult] = []
    eo_results: List[EqualOpportunityResult] = []

    # Group by protected attribute
    by_attr: Dict[ProtectedAttribute, List[OutcomeRecord]] = {}
    for r in records:
        by_attr.setdefault(r.protected_attribute, []).append(r)

    for attr, group in by_attr.items():
        # Split into reference vs protected
        protected = [r for r in group if not r.is_reference_group]
        reference = [r for r in group if r.is_reference_group]

        # Group protected by value (e.g. female, non-binary)
        by_value: Dict[str, List[OutcomeRecord]] = {}
        for r in protected:
            by_value.setdefault(r.protected_value, []).append(r)

        for value, value_records in by_value.items():
            di_results.append(compute_disparate_impact_ratio(
                protected_records=value_records,
                reference_records=reference))

            eo_results.append(compute_equal_opportunity_difference(
                protected_records=value_records,
                reference_records=reference))

    # Overall verdict
    has_violation = (
        any(r.verdict == FairnessVerdict.POTENTIAL_DISPARATE_IMPACT
              for r in di_results)
        or any(r.verdict == FairnessVerdict.POTENTIAL_DISPARATE_IMPACT
                  for r in eo_results))
    overall = (
        FairnessVerdict.POTENTIAL_DISPARATE_IMPACT if has_violation
        else FairnessVerdict.PASS)

    return FairnessReport(
        entity_name=entity_name,
        period_start=period_start,
        period_end=period_end,
        n_total_applications=len(records),
        disparate_impact_results=tuple(di_results),
        equal_opportunity_results=tuple(eo_results),
        overall_verdict=overall,
        notes=(
            f"Tested {len(by_attr)} protected attributes; "
            f"{len(di_results)} DIR + {len(eo_results)} EOD tests"))


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_outcomes(n_approve, n_decline, attr=ProtectedAttribute.GENDER,
                     value="FEMALE", is_ref=False, actual=None):
    out = []
    for i in range(n_approve):
        out.append(OutcomeRecord(
            application_id=f"{value}-A{i}",
            decision="APPROVE",
            protected_attribute=attr,
            protected_value=value,
            is_reference_group=is_ref,
            actual_outcome=actual))
    for i in range(n_decline):
        out.append(OutcomeRecord(
            application_id=f"{value}-D{i}",
            decision="DECLINE",
            protected_attribute=attr,
            protected_value=value,
            is_reference_group=is_ref,
            actual_outcome=actual))
    return out


def _test_dir_pass_when_close():
    """Approve rate 80% / 90% = 0.89 ratio → PASS."""
    protected = _make_outcomes(80, 20)         # 80% approve
    reference = _make_outcomes(90, 10, value="MALE", is_ref=True)
    r = compute_disparate_impact_ratio(
        protected_records=protected, reference_records=reference)
    assert r.verdict == FairnessVerdict.PASS
    assert r.disparate_impact_ratio is not None
    assert r.disparate_impact_ratio > FOUR_FIFTHS_THRESHOLD


def _test_dir_fails_when_disparate():
    """50% / 90% = 0.555 ratio → POTENTIAL_DISPARATE_IMPACT."""
    protected = _make_outcomes(50, 50)         # 50% approve
    reference = _make_outcomes(90, 10, value="MALE", is_ref=True)
    r = compute_disparate_impact_ratio(
        protected_records=protected, reference_records=reference)
    assert r.verdict == FairnessVerdict.POTENTIAL_DISPARATE_IMPACT
    assert r.disparate_impact_ratio < FOUR_FIFTHS_THRESHOLD


def _test_dir_insufficient_sample():
    """<30 records each → INSUFFICIENT_DATA."""
    protected = _make_outcomes(10, 5)
    reference = _make_outcomes(15, 5, value="MALE", is_ref=True)
    r = compute_disparate_impact_ratio(
        protected_records=protected, reference_records=reference)
    assert r.verdict == FairnessVerdict.INSUFFICIENT_DATA


def _test_dir_reference_no_approvals():
    """Reference has 0% approve → REFERENCE_GROUP_NO_APPROVALS."""
    protected = _make_outcomes(80, 20)
    reference = _make_outcomes(0, 100, value="MALE", is_ref=True)
    r = compute_disparate_impact_ratio(
        protected_records=protected, reference_records=reference)
    assert r.verdict == FairnessVerdict.REFERENCE_GROUP_NO_APPROVALS


def _test_dir_threshold_boundary():
    """At exactly threshold = PASS."""
    protected = _make_outcomes(80, 20)         # 80% approve
    reference = _make_outcomes(100, 0, value="MALE", is_ref=True)  # 100%
    r = compute_disparate_impact_ratio(
        protected_records=protected, reference_records=reference)
    # 80%/100% = 0.80 = threshold → PASS
    assert r.verdict == FairnessVerdict.PASS


def _test_eod_pass_when_balanced():
    protected = _make_outcomes(40, 10, actual="CREDITWORTHY")
    reference = _make_outcomes(45, 5, value="MALE", is_ref=True,
                                  actual="CREDITWORTHY")
    r = compute_equal_opportunity_difference(
        protected_records=protected, reference_records=reference)
    # tpr_p = 40/50 = 0.8; tpr_r = 45/50 = 0.9; eod = -0.1; abs=0.10 boundary
    # Threshold is 0.10 — abs=0.10 is NOT > 0.10 → PASS
    assert r.verdict == FairnessVerdict.PASS


def _test_eod_fails_when_imbalanced():
    protected = _make_outcomes(20, 30, actual="CREDITWORTHY")  # tpr=40%
    reference = _make_outcomes(45, 5, value="MALE", is_ref=True,
                                  actual="CREDITWORTHY")          # tpr=90%
    r = compute_equal_opportunity_difference(
        protected_records=protected, reference_records=reference)
    assert r.verdict == FairnessVerdict.POTENTIAL_DISPARATE_IMPACT


def _test_eod_insufficient():
    protected = _make_outcomes(2, 1, actual="CREDITWORTHY")
    reference = _make_outcomes(3, 1, value="MALE", is_ref=True,
                                  actual="CREDITWORTHY")
    r = compute_equal_opportunity_difference(
        protected_records=protected, reference_records=reference)
    assert r.verdict == FairnessVerdict.INSUFFICIENT_DATA


def _test_lda_latent_search_basic():
    """Records with topical clustering should reveal approval skew."""
    records = []
    # Topic A: 30 records, 90% approve
    for i in range(27):
        records.append(OutcomeRecord(
            application_id=f"A{i}", decision="APPROVE",
            protected_attribute=ProtectedAttribute.RACE,
            protected_value="CAUCASIAN", is_reference_group=True,
            application_features_text="employed engineer software"))
    for i in range(3):
        records.append(OutcomeRecord(
            application_id=f"AD{i}", decision="DECLINE",
            protected_attribute=ProtectedAttribute.RACE,
            protected_value="CAUCASIAN", is_reference_group=True,
            application_features_text="employed engineer software"))
    # Topic B: 30 records, 30% approve
    for i in range(9):
        records.append(OutcomeRecord(
            application_id=f"B{i}", decision="APPROVE",
            protected_attribute=ProtectedAttribute.RACE,
            protected_value="OTHER", is_reference_group=False,
            application_features_text="unemployed cleaner casual"))
    for i in range(21):
        records.append(OutcomeRecord(
            application_id=f"BD{i}", decision="DECLINE",
            protected_attribute=ProtectedAttribute.RACE,
            protected_value="OTHER", is_reference_group=False,
            application_features_text="unemployed cleaner casual"))

    topics = lda_latent_bias_search(records)
    # Should identify at least one topic
    assert len(topics) > 0
    # The topics should have non-trivial deltas
    has_biased = any(t.is_potentially_biased for t in topics)
    assert has_biased


def _test_lda_empty_records():
    topics = lda_latent_bias_search([])
    assert topics == ()


def _test_full_fairness_report():
    """End-to-end report generation."""
    protected = _make_outcomes(40, 60)
    reference = _make_outcomes(80, 20, value="MALE", is_ref=True)
    report = generate_fairness_report(
        entity_name="Test Bank",
        period_start="2025-01-01", period_end="2025-12-31",
        records=protected + reference)
    assert report.n_total_applications == 200
    assert len(report.disparate_impact_results) >= 1
    assert report.has_violations()


def _test_outcome_record_validates_decision():
    try:
        OutcomeRecord(
            application_id="X", decision="MAYBE",
            protected_attribute=ProtectedAttribute.GENDER,
            protected_value="X", is_reference_group=False)
        assert False
    except ValueError:
        pass


def _test_decimal_purity():
    protected = _make_outcomes(50, 50)
    reference = _make_outcomes(80, 20, value="MALE", is_ref=True)
    r = compute_disparate_impact_ratio(
        protected_records=protected, reference_records=reference)
    assert isinstance(r.disparate_impact_ratio, Decimal)


def self_test() -> None:
    tests = [
        _test_dir_pass_when_close,
        _test_dir_fails_when_disparate,
        _test_dir_insufficient_sample,
        _test_dir_reference_no_approvals,
        _test_dir_threshold_boundary,
        _test_eod_pass_when_balanced,
        _test_eod_fails_when_imbalanced,
        _test_eod_insufficient,
        _test_lda_latent_search_basic,
        _test_lda_empty_records,
        _test_full_fairness_report,
        _test_outcome_record_validates_decision,
        _test_decimal_purity,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ fairness_testing self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ fairness_testing self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
